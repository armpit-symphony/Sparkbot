"""Run from the server checkout; credentials stay in memory, output is status only."""
import json
import uuid
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = ("https://sparkpitlabs.com/api/v1" if "--https" in sys.argv
        else "http://127.0.0.1:8002/api/v1")


def call(method, path, body=None, token=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                      headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            code, payload = response.status, response.read()
    except HTTPError as exc:
        code, payload = exc.code, exc.read()
    if code not in (expected if isinstance(expected, tuple) else (expected,)):
        raise RuntimeError(f"{method} {path}: expected {expected}, received {code}")
    return json.loads(payload) if payload else None


env = dict(line.split("=", 1) for line in Path(__file__).with_name(".env").read_text().splitlines()
           if line and not line.startswith("#"))
call("POST", "/chat/users/login", {"passphrase": "incorrect-smoke-passphrase"}, expected=401)
owner = call("POST", "/chat/users/login", {"passphrase": env["SPARKBOT_PASSPHRASE"]})["access_token"]
rooms, seats = [], []
try:
    for label in ("participants", "private"):
        rooms.append(call("POST", "/chat/rooms/", {"name": "RT005 smoke " + label}, owner)["id"])
    call("POST", f"/chat/rooms/{rooms[0]}/roundtable/messages",
         {"content": "RT008 owner message without model configuration"}, owner, 201)
    with urlopen(BASE + "/chat/seats/connector.py", timeout=30) as response:
        assert response.status == 200 and b"class McpServer" in response.read()
    for index, kind in enumerate(("human", "human", "agent", "agent")):
        seat = call("POST", f"/chat/rooms/{rooms[0]}/seats",
                    {"display_name": f"Smoke {kind} {index}", "slug": "smoke-" + uuid.uuid4().hex[:12],
                     "kind": kind}, owner, 201)
        seats.append(seat)
        assert call("GET", f"/chat/rooms/{rooms[0]}", token=owner)["meeting_mode_enabled"]
        token = call("POST", "/chat/seats/token", {"key": seat["key"]})["access_token"]
        me = call("GET", "/chat/seats/me", token=token)
        assert me["seat"]["id"] == seat["id"]
        call("POST", f"/chat/seats/rooms/{rooms[0]}/messages",
             {"content": f"RT005 synthetic message from participant {index}"}, token, (200, 201))
        call("GET", f"/chat/seats/rooms/{rooms[0]}/messages", token=token)
        call("GET", f"/chat/seats/rooms/{rooms[1]}/messages", token=token, expected=(403, 404))
        call("GET", "/chat/rooms/", token=token, expected=403)
        call("DELETE", f"/chat/rooms/{rooms[0]}/seats/{seat['id']}", token=owner, expected=(200, 204))
        call("GET", "/chat/seats/me", token=token, expected=(401, 403))
        call("POST", "/chat/seats/token", {"key": seat["key"]}, expected=(401, 403))
    print("PASS: model-free owner posting; connector download; meeting discovery flag; wrong-password rejection; two human and two agent identities; read/post; cross-room denial; ordinary-route denial; token/key revocation.")
finally:
    for room_id in reversed(rooms):
        call("DELETE", f"/chat/rooms/{room_id}", token=owner)
    print("Synthetic smoke rooms removed; no credentials printed.")
