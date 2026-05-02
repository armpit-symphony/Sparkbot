from __future__ import annotations

import base64
from typing import Any


IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}

_IMAGE_MAGIC: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),
]
_WEBP_MARKER = b"WEBP"

_VISION_MODEL_FALLBACKS = [
    "gpt-4o-mini",
    "gpt-4o",
    "openrouter/openai/gpt-4o-mini",
    "gemini/gemini-2.0-flash",
    "claude-sonnet-4-5",
]


def detect_image_type(data: bytes) -> str | None:
    for magic, mime in _IMAGE_MAGIC:
        if data[: len(magic)] == magic:
            if mime == "image/webp":
                if len(data) >= 12 and data[8:12] == _WEBP_MARKER:
                    return mime
                return None
            return mime
    return None


def image_data_url(data: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(data).decode()}"


def build_vision_user_message(data: bytes, content_type: str, prompt: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": image_data_url(data, content_type)}},
            {"type": "text", "text": prompt.strip() or "Describe this image and note anything relevant."},
        ],
    }


def _looks_vision_capable(model: str) -> bool:
    normalized = (model or "").strip().lower()
    if not normalized:
        return False
    if normalized.startswith("ollama/"):
        return any(marker in normalized for marker in ("llava", "bakllava", "moondream", "vision"))
    return any(
        marker in normalized
        for marker in (
            "gpt-4o",
            "gpt-4.1",
            "gpt-5",
            "gemini",
            "claude",
            "vision",
            "multi",
        )
    )


def resolve_vision_model(preferred_model: str | None) -> str | None:
    from app.api.routes.chat.llm import model_is_configured

    preferred = (preferred_model or "").strip()
    if preferred and _looks_vision_capable(preferred) and model_is_configured(preferred):
        return preferred

    for candidate in _VISION_MODEL_FALLBACKS:
        if model_is_configured(candidate):
            return candidate

    return None
