import os
from typing import Optional

try:
    import whisper
except Exception:  # pragma: no cover - 本地没有安装时降级
    whisper = None

_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        if whisper is None:
            raise RuntimeError("openai-whisper is not installed")
        model_size = os.getenv("WHISPER_MODEL_SIZE", "base")
        _MODEL = whisper.load_model(model_size)
    return _MODEL


def transcribe_audio(file_path: str) -> str:
    model = _get_model()
    result = model.transcribe(file_path)
    return result.get("text", "")
