"""Local speech-to-text with timestamps (no API key, runs on your computer).

Uses Whisper through sherpa-onnx, with Silero voice detection to split speech
into timestamped segments. Models download once from the sherpa-onnx GitHub
releases into data/models/.
"""
from __future__ import annotations

import bz2
import json
import subprocess
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"
SR = 16000


@dataclass
class Segment:
    start: float
    end: float
    text: str


def _download(url: str, dest: Path) -> None:
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(dest)


def ensure_models(models_dir: str | Path, name: str = "small.en", log=print) -> tuple[Path, Path]:
    models_dir = Path(models_dir)
    mdir = models_dir / f"whisper-{name}"
    need = [f"{name}-encoder.int8.onnx", f"{name}-decoder.int8.onnx", f"{name}-tokens.txt"]
    if not all((mdir / n).exists() for n in need):
        log(f"downloading speech model whisper {name} (one time)...")
        import requests

        mdir.mkdir(parents=True, exist_ok=True)
        url = f"{RELEASES}/sherpa-onnx-whisper-{name}.tar.bz2"
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            r.raw.decode_content = True
            with tarfile.open(fileobj=bz2.BZ2File(r.raw), mode="r|") as tar:
                for m in tar:  # keep only the small int8 files
                    base = Path(m.name).name
                    if base in need and m.isfile():
                        src = tar.extractfile(m)
                        (mdir / base).write_bytes(src.read())
    vad = models_dir / "silero_vad.onnx"
    if not vad.exists():
        _download(f"{RELEASES}/silero_vad.onnx", vad)
    return mdir, vad


def load_audio(path: str | Path):
    import numpy as np

    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True,
    )
    return np.frombuffer(out.stdout, dtype=np.float32)


def speech_segments(samples, vad_model: Path, max_len: float = 20.0) -> list[tuple[float, float, object]]:
    import sherpa_onnx

    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = str(vad_model)
    cfg.silero_vad.min_silence_duration = 0.3
    cfg.silero_vad.min_speech_duration = 0.25
    cfg.silero_vad.max_speech_duration = max_len  # whisper handles <= 30s at a time
    cfg.sample_rate = SR
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=max(60, len(samples) / SR + 5))
    win = cfg.silero_vad.window_size
    out = []

    def drain():
        while not vad.empty():
            seg = vad.front
            out.append((seg.start / SR, (seg.start + len(seg.samples)) / SR, seg.samples))
            vad.pop()

    for i in range(0, len(samples), win):
        vad.accept_waveform(samples[i:i + win])
        drain()
    vad.flush()
    drain()
    return out


def transcribe(path: str | Path, models_dir: str | Path, name: str = "small.en", threads: int = 4,
               log=print) -> list[Segment]:
    """Timestamped transcript. Cached next to the media file as <file>.transcript.json."""
    path = Path(path)
    cache = path.with_suffix(path.suffix + ".transcript.json")
    if cache.exists():
        return [Segment(**s) for s in json.loads(cache.read_text())]
    import sherpa_onnx

    mdir, vad = ensure_models(models_dir, name, log)
    rec = sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=str(mdir / f"{name}-encoder.int8.onnx"), decoder=str(mdir / f"{name}-decoder.int8.onnx"),
        tokens=str(mdir / f"{name}-tokens.txt"), language="en" if name.endswith(".en") else "",
        task="transcribe", num_threads=threads,
    )
    samples = load_audio(path)
    segs: list[Segment] = []
    for start, end, chunk in speech_segments(samples, vad):
        s = rec.create_stream()
        s.accept_waveform(SR, chunk)
        rec.decode_stream(s)
        text = s.result.text.strip()
        if text:
            segs.append(Segment(round(start, 2), round(end, 2), text))
    cache.write_text(json.dumps([asdict(s) for s in segs]))
    return segs
