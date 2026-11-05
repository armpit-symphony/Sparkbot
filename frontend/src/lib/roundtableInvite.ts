// Roundtable invites: the text an owner pastes to an outside agent, and the
// link a guest person opens. Pure functions so they can be unit-tested.

export interface InvitedSeat {
  id: string
  slug: string
  display_name: string
  kind: "agent" | "human"
  key: string
}

export interface InviteContext {
  /** Origin that serves /api/v1, e.g. "https://sparkpitlabs.com". */
  serverUrl: string
  roomId: string
  roomName: string
}

const CONNECTOR_FALLBACK_URL =
  "https://raw.githubusercontent.com/armpit-symphony/Sparkbot/main/sparkbot-roundtable.py"

export function trimSlash(value: string): string {
  return value.replace(/\/+$/, "")
}

/** "/roundtable/meeting/abc" -> "/roundtable"; "/meeting/abc" -> "". */
export function appBasePath(pathname: string): string {
  const marker = pathname.indexOf("/meeting/")
  return marker >= 0 ? trimSlash(pathname.slice(0, marker)) : ""
}

/** Seat key goes in the URL fragment so it is never sent to a server or logged. */
export function buildGuestLink(
  origin: string,
  basePath: string,
  seat: InvitedSeat,
  ctx: InviteContext,
): string {
  const params = new URLSearchParams({ key: seat.key, room: ctx.roomId })
  return `${trimSlash(origin)}${trimSlash(basePath)}/guest#${params.toString()}`
}

export function parseGuestFragment(
  hash: string,
): { key: string; roomId: string } | null {
  const params = new URLSearchParams(hash.replace(/^#/, ""))
  const key = (params.get("key") ?? "").trim()
  if (!key.startsWith("rts_")) return null
  return { key, roomId: (params.get("room") ?? "").trim() }
}

export function suggestSlug(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 31)
  return slug.length >= 2 ? slug : `${slug || "guest"}-seat`.slice(0, 31)
}

/** Everything an AI agent (Codex, Claude Code, any script) needs, in one paste. */
export function buildAgentInvite(
  seat: InvitedSeat,
  ctx: InviteContext,
): string {
  const server = trimSlash(ctx.serverUrl)
  const api = `${server}/api/v1/chat`
  const profile = seat.slug
  return [
    `You're invited to a Sparkbot Roundtable meeting room as "${seat.display_name}" (@${seat.slug}).`,
    "Humans and other AI agents coordinate there. Before starting work, read what's new;",
    `post short status updates and handoffs; answer messages addressed to @${seat.slug}.`,
    "",
    `Room: ${ctx.roomName}  (id ${ctx.roomId})`,
    `Server: ${server}`,
    `Your seat key (private, this room only, the owner can revoke it): ${seat.key}`,
    "",
    "OPTION A - MCP tools (best). Needs Python 3.10+, nothing to install.",
    `1. Download the connector: ${api}/seats/connector.py`,
    `   (if that 404s: ${CONNECTOR_FALLBACK_URL})`,
    "2. Save your seat (the key is read from an env var, not typed on the command line):",
    `   PowerShell:  $env:SPARKBOT_SEAT_KEY="${seat.key}"; python sparkbot-roundtable.py login --profile ${profile} --url ${server}`,
    `   bash/zsh:    SPARKBOT_SEAT_KEY="${seat.key}" python sparkbot-roundtable.py login --profile ${profile} --url ${server}`,
    `3. Register an MCP server named "roundtable": command "python", args ["<full path>/sparkbot-roundtable.py", "mcp", "--profile", "${profile}"].`,
    "   Codex: add it under [mcp_servers.roundtable] in ~/.codex/config.toml.",
    `   Claude Code: claude mcp add --scope user --transport stdio roundtable -- python <full path>/sparkbot-roundtable.py mcp --profile ${profile}`,
    "   Then restart so the tools load: roundtable_read, roundtable_post, roundtable_wait, roundtable_whoami.",
    "",
    "OPTION B - plain HTTP (works anywhere, no setup):",
    `1. POST ${api}/seats/token  with JSON {"key": "<seat key>"}  -> access_token (valid 12h)`,
    `2. GET  ${api}/seats/rooms/${ctx.roomId}/messages?after_id=<last id you saw>  with header Authorization: Bearer <access_token>`,
    `3. POST ${api}/seats/rooms/${ctx.roomId}/messages  with JSON {"content": "..."}`,
    "",
    "Never put this key in shared files or repos. When you're set up, post a short hello in the room.",
  ].join("\n")
}
