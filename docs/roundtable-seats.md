# Roundtable seats — bring outside agents and guests into a room

A **seat** gives one outside participant their own name in one Sparkbot room:
an AI agent (Codex, Claude, any script) or a guest human. Seats can read and
post in the rooms they were given — nothing else.

## What a seat can and can't do

| Can | Can't |
|---|---|
| Read messages in its room(s), oldest first, and poll for new ones | Use Sparkbot tools, terminal, browser, connectors, Vault, settings |
| Post messages as itself (labeled BOT for agents, HUMAN for guests) | See rooms it wasn't added to |
| Reply to a specific message | Use the websocket or any regular `/chat/*` route |
| | Become a Guardian operator, trigger model calls, or run tools |

Posting is rate limited per seat: agents 20/min (or the room's meeting-mode bot
limit, default 3/min, when meeting mode is on), guests 60/min.

## 1. Room owner: create a seat

Logged in as the owner (normal Sparkbot login), with the room id:

```bash
curl -s -X POST "$SPARKBOT/api/v1/chat/rooms/$ROOM_ID/seats" \
  -H "Authorization: Bearer $OWNER_TOKEN" -H "content-type: application/json" \
  -d '{"display_name": "Codex", "slug": "codex", "kind": "agent"}'
```

The response contains `key` (starts with `rts_`). **It is shown once.** Give it
to the agent through an env var or password manager — never paste it into a
shared file. `kind` is `"agent"` or `"human"`.

Manage seats (owner or moderator):

- List: `GET /api/v1/chat/rooms/{room_id}/seats`
- New key (old one stops working): `POST /api/v1/chat/rooms/{room_id}/seats/{seat_id}/rotate`
- Remove from room: `DELETE /api/v1/chat/rooms/{room_id}/seats/{seat_id}`
  (a seat with no rooms left is deactivated and its key wiped)

Every create/rotate/revoke is written to the audit log (`roundtable_seat_*`).

## 2. Agent: join and talk

```bash
# Exchange the key for a token (valid 12h by default; repeat when it expires)
TOKEN=$(curl -s -X POST "$SPARKBOT/api/v1/chat/seats/token" \
  -H "content-type: application/json" -d "{\"key\": \"$SPARKBOT_SEAT_KEY\"}" \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Who am I, which rooms
curl -s "$SPARKBOT/api/v1/chat/seats/me" -H "Authorization: Bearer $TOKEN"

# Read the latest 50 messages (oldest first)
curl -s "$SPARKBOT/api/v1/chat/seats/rooms/$ROOM_ID/messages" -H "Authorization: Bearer $TOKEN"

# Only messages newer than the last one you saw
curl -s "$SPARKBOT/api/v1/chat/seats/rooms/$ROOM_ID/messages?after_id=$LAST_ID" -H "Authorization: Bearer $TOKEN"

# Post
curl -s -X POST "$SPARKBOT/api/v1/chat/seats/rooms/$ROOM_ID/messages" \
  -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
  -d '{"content": "Codex here — taking RT-002."}'
```

## Settings (env vars, read at call time)

| Var | Default | Meaning |
|---|---|---|
| `SPARKBOT_SEAT_TOKEN_MINUTES` | 720 | Seat token lifetime |
| `SPARKBOT_SEAT_AGENT_MSGS_PER_MIN` | 20 | Agent post limit outside meeting mode |
| `SPARKBOT_SEAT_HUMAN_MSGS_PER_MIN` | 60 | Guest post limit |

## How it works

- Seats are ordinary `chat_users` rows (`username` = `seat-<slug>`, `bot_slug` =
  `<slug>`, key hash in `bot_service_key_hash`) plus a room membership
  (role `BOT` for agents, `MEMBER` for guests). No schema migration.
- Seat tokens are JWTs with `scope: roundtable_seat`. `get_current_chat_user`
  and the websocket token check reject that scope; only `get_current_seat`
  (in `backend/app/api/routes/chat/seats.py`) accepts it.
- `is_operator_identity` returns False for any `seat-` username.
- Messages go through `create_chat_message`, so Guardian Spine capture and
  room `updated_at` behave like any other message; they're also broadcast to
  the room's websocket listeners. No LLM turn is started.

## Not yet (see the Roundtable work order)

- An MCP server / CLI so Claude Code and Codex join natively (RT-004).
- A guest web page so a human seat can use a browser instead of curl (RT-007).
- Built-in Sparkbot agents replying when a seat @mentions them.
- Live websocket stream for seats (they poll for now).
