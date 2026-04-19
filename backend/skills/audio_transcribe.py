"""
Sparkbot skill: audio_transcribe

Transcribe audio files and podcasts using OpenAI Whisper API.
Accepts local file paths or URLs (downloads first).

Tools:
  transcribe_audio(source, language="", prompt="")

Env vars:
  OPENAI_API_KEY — required for Whisper API
  WHISPER_MODEL  — default "whisper-1"

Supports: mp3, mp4, mpeg, mpga, m4a, wav, webm (Whisper limits: 25 MB)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import httpx

_OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "").strip()
_WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1").strip()
_MAX_BYTES     = 25 * 1024 * 1024  # 25 MB Whisper limit

DEFINITION = {
    "type": "function",
    "function": {
        "name": "transcribe_audio",
        "description": (
            "Transcribe an audio file or podcast using OpenAI Whisper. "
            "Accepts a local file path or a URL to an audio file (mp3, mp4, m4a, wav, webm). "
            "Use for: 'transcribe this podcast', 'what does this audio say', 'convert this recording to text'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Local file path or URL to the audio file",
                },
                "language": {
                    "type": "string",
                    "description": "ISO-639-1 language code (e.g. 'en', 'es', 'fr'). Auto-detected if omitted.",
                },
                "prompt": {
                    "type": "string",
                    "description": "Optional context hint to improve accuracy (names, technical terms).",
                },
            },
            "required": ["source"],
        },
    },
}

POLICY = {
    "scope": "read",
    "resource": "web",
    "default_action": "allow",
    "action_type": "read",
    "high_risk": False,
    "requires_execution_gate": False,
}


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    if not _OPENAI_KEY:
        return "Error: OPENAI_API_KEY is required for audio transcription."

    source   = (args.get("source") or "").strip()
    language = (args.get("language") or "").strip()
    prompt   = (args.get("prompt") or "").strip()

    if not source:
        return "Error: source (file path or URL) is required."

    audio_bytes: bytes
    filename: str

    if source.startswith("http://") or source.startswith("https://"):
        # Download the audio
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                r = await client.get(source)
                r.raise_for_status()
                audio_bytes = r.content
                # Try to get filename from URL
                filename = source.split("/")[-1].split("?")[0] or "audio.mp3"
        except Exception as e:
            return f"Failed to download audio: {e}"
    else:
        p = Path(source)
        if not p.exists():
            return f"File not found: {source}"
        audio_bytes = p.read_bytes()
        filename = p.name

    if len(audio_bytes) > _MAX_BYTES:
        mb = len(audio_bytes) / 1024 / 1024
        return f"File too large ({mb:.1f} MB). Whisper accepts up to 25 MB. Please trim the audio first."

    # Call Whisper API
    try:
        data: dict = {}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt
        data["model"] = _WHISPER_MODEL

        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {_OPENAI_KEY}"},
                files={"file": (filename, audio_bytes, "audio/mpeg")},
                data=data,
            )
        if r.status_code != 200:
            return f"Whisper API error {r.status_code}: {r.text[:400]}"
        text = r.json().get("text", "")
        word_count = len(text.split())
        return f"**Transcription** ({word_count} words):\n\n{text}"
    except Exception as e:
        return f"Transcription failed: {e}"
