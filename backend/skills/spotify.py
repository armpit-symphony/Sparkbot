"""
Sparkbot skill: spotify

Control Spotify playback and search for music via the Spotify Web API.

Tools:
  spotify_play(query="", uri="")        — play a track, album, artist, or playlist by name/URI
  spotify_pause()                       — pause playback
  spotify_next()                        — skip to next track
  spotify_previous()                    — go back to previous track
  spotify_now_playing()                 — what's currently playing
  spotify_search(query, type="track")   — search tracks, albums, artists, playlists
  spotify_volume(level)                 — set volume 0–100

Env vars (create an app at developer.spotify.com):
  SPOTIFY_CLIENT_ID       — Spotify app client ID
  SPOTIFY_CLIENT_SECRET   — Spotify app client secret
  SPOTIFY_REFRESH_TOKEN   — OAuth refresh token (requires user authorization once)

Scopes needed:
  user-read-playback-state user-modify-playback-state user-read-currently-playing
"""
from __future__ import annotations

import base64
import os
import time

import httpx

_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
_REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN", "").strip()

_API = "https://api.spotify.com/v1"
_TOKEN_CACHE: dict = {}


async def _get_token() -> tuple[str | None, str | None]:
    if not (_CLIENT_ID and _CLIENT_SECRET and _REFRESH_TOKEN):
        return None, "Spotify not configured. Set SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN."
    if _TOKEN_CACHE.get("token") and time.time() < _TOKEN_CACHE.get("expires", 0) - 60:
        return _TOKEN_CACHE["token"], None
    creds = base64.b64encode(f"{_CLIENT_ID}:{_CLIENT_SECRET}".encode()).decode()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": _REFRESH_TOKEN},
        )
    if r.status_code != 200:
        return None, f"Spotify auth error {r.status_code}: {r.text[:200]}"
    d = r.json()
    token = d.get("access_token")
    if not token:
        return None, "Spotify: no access_token returned."
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expires"] = time.time() + int(d.get("expires_in", 3600))
    return token, None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _spotify_play(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    query = (args.get("query") or "").strip()
    uri   = (args.get("uri") or "").strip()

    payload: dict = {}
    if uri:
        if uri.startswith("spotify:track:"):
            payload = {"uris": [uri]}
        else:
            payload = {"context_uri": uri}
    elif query:
        # Search for the track first
        async with httpx.AsyncClient(timeout=10.0) as client:
            sr = await client.get(
                f"{_API}/search",
                headers=_headers(token),
                params={"q": query, "type": "track,playlist,album", "limit": 1},
            )
        if sr.status_code != 200:
            return f"Spotify search error: {sr.text[:200]}"
        results = sr.json()
        track = (results.get("tracks", {}).get("items") or [None])[0]
        album = (results.get("albums", {}).get("items") or [None])[0]
        playlist = (results.get("playlists", {}).get("items") or [None])[0]
        if track:
            payload = {"uris": [track["uri"]]}
            name = track["name"] + " by " + ", ".join(a["name"] for a in track["artists"])
        elif album:
            payload = {"context_uri": album["uri"]}
            name = album["name"]
        elif playlist:
            payload = {"context_uri": playlist["uri"]}
            name = playlist["name"]
        else:
            return f"Nothing found for '{query}' on Spotify."
    else:
        # Resume playback
        payload = {}
        name = "playback"

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.put(f"{_API}/me/player/play", headers=_headers(token), json=payload)
    if r.status_code in (200, 202, 204):
        return f"▶ Playing: **{name}**" if query or uri else "▶ Playback resumed."
    if r.status_code == 404:
        return "No active Spotify device found. Open Spotify on a device first."
    return f"Spotify play error {r.status_code}: {r.text[:200]}"


async def _spotify_pause(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.put(f"{_API}/me/player/pause", headers=_headers(token))
    return "⏸ Paused." if r.status_code in (200, 202, 204) else f"Error: {r.text[:200]}"


async def _spotify_next(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(f"{_API}/me/player/next", headers=_headers(token))
    return "⏭ Skipped to next track." if r.status_code in (200, 202, 204) else f"Error: {r.text[:200]}"


async def _spotify_previous(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(f"{_API}/me/player/previous", headers=_headers(token))
    return "⏮ Previous track." if r.status_code in (200, 202, 204) else f"Error: {r.text[:200]}"


async def _spotify_now_playing(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{_API}/me/player/currently-playing", headers=_headers(token))
    if r.status_code == 204:
        return "Nothing playing right now."
    if r.status_code != 200:
        return f"Error: {r.text[:200]}"
    d = r.json()
    item = d.get("item") or {}
    name    = item.get("name", "?")
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    album   = item.get("album", {}).get("name", "")
    is_playing = d.get("is_playing", False)
    progress_ms = d.get("progress_ms", 0)
    duration_ms = item.get("duration_ms", 1)
    progress = f"{progress_ms // 60000}:{(progress_ms // 1000) % 60:02d}"
    total    = f"{duration_ms // 60000}:{(duration_ms // 1000) % 60:02d}"
    status = "▶" if is_playing else "⏸"
    return f"{status} **{name}** by {artists}\n  Album: {album}\n  {progress} / {total}"


async def _spotify_search(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    query   = (args.get("query") or "").strip()
    type_   = (args.get("type") or "track").strip().lower()
    if not query:
        return "Error: query is required."
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{_API}/search",
            headers=_headers(token),
            params={"q": query, "type": type_, "limit": 8},
        )
    if r.status_code != 200:
        return f"Spotify search error: {r.text[:200]}"
    results = r.json()
    items = results.get(f"{type_}s", {}).get("items", [])
    if not items:
        return f"No {type_}s found for '{query}'."
    lines = [f"**Spotify {type_.title()} results for '{query}':**", ""]
    for item in items:
        if type_ == "track":
            artists = ", ".join(a["name"] for a in item.get("artists", []))
            lines.append(f"• **{item['name']}** by {artists}  `{item['uri']}`")
        elif type_ == "artist":
            lines.append(f"• **{item['name']}**  `{item['uri']}`")
        elif type_ in ("album", "playlist"):
            owner = item.get("owner", {}).get("display_name", "") or ""
            lines.append(f"• **{item['name']}**" + (f" by {owner}" if owner else "") + f"  `{item['uri']}`")
    return "\n".join(lines)


async def _spotify_volume(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    level = max(0, min(100, int(args.get("level") or 50)))
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.put(f"{_API}/me/player/volume", headers=_headers(token), params={"volume_percent": level})
    return f"🔊 Volume set to {level}%." if r.status_code in (200, 202, 204) else f"Error: {r.text[:200]}"


DEFINITIONS = [
    {"type": "function", "function": {"name": "spotify_play", "description": "Play music on Spotify by name or URI. Resumes current track if no query given.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Track, artist, album, or playlist name"}, "uri": {"type": "string", "description": "Spotify URI from spotify_search"}}, "required": []}}},
    {"type": "function", "function": {"name": "spotify_pause", "description": "Pause Spotify playback.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "spotify_next", "description": "Skip to the next track on Spotify.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "spotify_previous", "description": "Go back to the previous track on Spotify.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "spotify_now_playing", "description": "Show what's currently playing on Spotify.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "spotify_search", "description": "Search Spotify for tracks, albums, artists, or playlists.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "type": {"type": "string", "description": "track, album, artist, or playlist (default: track)"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "spotify_volume", "description": "Set Spotify volume 0–100.", "parameters": {"type": "object", "properties": {"level": {"type": "integer"}}, "required": ["level"]}}},
]

POLICIES = {n["function"]["name"]: {
    "scope": "write" if n["function"]["name"] in ("spotify_play","spotify_pause","spotify_next","spotify_previous","spotify_volume") else "read",
    "resource": "local_machine",
    "default_action": "allow",
    "action_type": "data_write" if n["function"]["name"] not in ("spotify_now_playing","spotify_search") else "data_read",
    "high_risk": False, "requires_execution_gate": False,
} for n in DEFINITIONS}

_EXECUTORS = {
    "spotify_play": _spotify_play, "spotify_pause": _spotify_pause,
    "spotify_next": _spotify_next, "spotify_previous": _spotify_previous,
    "spotify_now_playing": _spotify_now_playing, "spotify_search": _spotify_search,
    "spotify_volume": _spotify_volume,
}

DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["spotify_play"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await _spotify_play(args)


def _wrap(fn):
    async def _e(args: dict, *, user_id=None, room_id=None, session=None) -> str:
        return await fn(args)
    return _e


def _register_extra(registry) -> None:
    for defn in DEFINITIONS:
        name = defn["function"]["name"]
        if name not in registry.executors:
            registry.definitions.append(defn)
            registry.policies[name] = POLICIES[name]
            registry.executors[name] = _wrap(_EXECUTORS[name])
