"""
Sparkbot skill: youtube_summarize

Fetch YouTube video transcripts and return a summary or full transcript.
Uses the YouTube timedtext API (no API key required for auto-captions).
Falls back to yt-dlp for subtitle extraction if available.

Tools:
  youtube_transcript(url, language="en")   — get transcript/captions from a YouTube video
  youtube_summarize(url, language="en")    — transcript ready for LLM summarization
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

_YT_TIMEDTEXT = "https://www.youtube.com/api/timedtext"
_YT_WATCH     = "https://www.youtube.com/watch"


def _extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


async def _get_transcript_api(video_id: str, lang: str) -> str | None:
    """Try the YouTube timedtext API directly."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        # First get the watch page to find available tracks
        r = await client.get(
            _YT_WATCH,
            params={"v": video_id},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        if r.status_code != 200:
            return None
        # Look for timedtext URL in page source
        match = re.search(r'"timedtext".*?"baseUrl":"([^"]+)"', r.text)
        if not match:
            # Try direct timedtext API
            rt = await client.get(
                _YT_TIMEDTEXT,
                params={"v": video_id, "lang": lang, "fmt": "srv3"},
            )
            if rt.status_code != 200 or not rt.text.strip():
                return None
            return _parse_timedtext_xml(rt.text)
        base_url = match.group(1).replace("\\u0026", "&").replace("\\/", "/")
        rt = await client.get(base_url)
        if rt.status_code != 200:
            return None
        return _parse_timedtext_xml(rt.text)


def _parse_timedtext_xml(xml_text: str) -> str | None:
    try:
        root = ET.fromstring(xml_text)
        parts: list[str] = []
        for text_el in root.iter("text"):
            t = (text_el.text or "").strip()
            if t:
                parts.append(t)
        return " ".join(parts) if parts else None
    except ET.ParseError:
        return None


async def _get_transcript_ytdlp(video_id: str, lang: str) -> str | None:
    """Try yt-dlp as a fallback."""
    try:
        import shutil
        ytdlp = shutil.which("yt-dlp")
        if not ytdlp:
            return None
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [ytdlp, "--write-auto-subs", "--sub-lang", lang, "--skip-download",
                 "--sub-format", "vtt", "--output", f"{tmpdir}/%(id)s",
                 f"https://www.youtube.com/watch?v={video_id}"],
                capture_output=True, text=True, timeout=30,
            )
            vtt_files = list(Path(tmpdir).glob("*.vtt"))
            if not vtt_files:
                return None
            raw = vtt_files[0].read_text(encoding="utf-8", errors="replace")
            # Strip VTT formatting
            lines = []
            for line in raw.split("\n"):
                line = line.strip()
                if not line or line.startswith("WEBVTT") or "-->" in line or re.match(r"^\d+$", line):
                    continue
                line = re.sub(r"<[^>]+>", "", line)
                if line and (not lines or lines[-1] != line):
                    lines.append(line)
            return " ".join(lines) if lines else None
    except Exception:
        return None


async def _youtube_transcript(args: dict, **_) -> str:
    url  = (args.get("url") or "").strip()
    lang = (args.get("language") or "en").strip()
    if not url:
        return "Error: url is required."
    vid = _extract_video_id(url)
    if not vid:
        return f"Could not extract video ID from URL: {url}"

    transcript = await _get_transcript_api(vid, lang)
    if not transcript:
        transcript = await _get_transcript_ytdlp(vid, lang)
    if not transcript:
        return (
            f"Could not retrieve transcript for video {vid}. "
            "The video may not have captions, or they may be disabled. "
            "Try a different language code or use the YouTube website to check if captions are available."
        )
    word_count = len(transcript.split())
    # Truncate to ~12k chars for LLM context
    if len(transcript) > 12000:
        transcript = transcript[:12000] + "…\n\n_(transcript truncated at 12,000 chars)_"
    return f"**YouTube Transcript** — `{vid}` ({word_count} words)\n\n{transcript}"


async def _youtube_summarize_tool(args: dict, **_) -> str:
    """Fetches transcript and instructs the LLM to summarize it."""
    result = await _youtube_transcript(args)
    if result.startswith("Error") or result.startswith("Could not"):
        return result
    return result + "\n\n---\n_Transcript retrieved. Summarize the above content._"


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "youtube_transcript",
            "description": (
                "Fetch the transcript/captions from a YouTube video. "
                "Use when the user shares a YouTube URL and wants a summary, key points, or transcript. "
                "Works without an API key using YouTube auto-captions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "YouTube video URL"},
                    "language": {"type": "string", "description": "Caption language code (default: 'en')"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_summarize",
            "description": (
                "Fetch a YouTube video transcript and prepare it for summarization. "
                "Use when asked to 'summarize this YouTube video' — fetches the transcript "
                "then you summarize the returned content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "language": {"type": "string", "description": "Caption language code (default: 'en')"},
                },
                "required": ["url"],
            },
        },
    },
]

POLICIES = {
    "youtube_transcript": {"scope": "read", "resource": "web", "default_action": "allow", "action_type": "read", "high_risk": False, "requires_execution_gate": False},
    "youtube_summarize":  {"scope": "read", "resource": "web", "default_action": "allow", "action_type": "read", "high_risk": False, "requires_execution_gate": False},
}

DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["youtube_transcript"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await _youtube_transcript(args)


def _register_extra(registry) -> None:
    async def _summ(args, *, user_id=None, room_id=None, session=None): return await _youtube_summarize_tool(args)
    if "youtube_summarize" not in registry.executors:
        registry.definitions.append(DEFINITIONS[1])
        registry.policies["youtube_summarize"] = POLICIES["youtube_summarize"]
        registry.executors["youtube_summarize"] = _summ
