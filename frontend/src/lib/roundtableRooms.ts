import { apiFetch } from "@/lib/apiBase"

// Bring-your-own-agent Roundtable rooms: no Sparkbot model seats required.

export function defaultRoundtableName(now: Date = new Date()): string {
  const when = now.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
  return `Roundtable · ${when}`
}

/** Create a room in meeting mode (so it shows in meeting lists) and return its id. */
export async function createRoundtableRoom(name?: string): Promise<string> {
  const roomName = (name ?? "").trim() || defaultRoundtableName()
  const created = await apiFetch("/api/v1/chat/rooms/", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: roomName,
      description: "Roundtable: invite your own agents and people.",
    }),
  })
  if (!created.ok) throw new Error("Could not create the room.")
  const room = await created.json()
  await enableMeetingMode(room.id)
  return room.id as string
}

/** Turn on meeting mode (owner only). Safe to call more than once. */
export async function enableMeetingMode(roomId: string): Promise<boolean> {
  const res = await apiFetch(`/api/v1/chat/rooms/${roomId}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ meeting_mode_enabled: true }),
  })
  return res.ok
}
