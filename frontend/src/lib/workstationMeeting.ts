import { apiFetch } from "@/lib/apiBase"

export const ROUND_TABLE_SEAT_COUNT = 8

// ─── Task-meeting link ────────────────────────────────────────────────────────
// Maps a guardian task ID → the meeting room that was opened for it.

const TASK_MEETING_LINK_PREFIX = "sparkbot_task_meeting_link:"

export function saveTaskMeetingLink(taskId: string, roomId: string): void {
  if (typeof window === "undefined") return
  window.localStorage.setItem(`${TASK_MEETING_LINK_PREFIX}${taskId}`, roomId)
}

export function loadTaskMeetingLink(taskId: string): string | null {
  if (typeof window === "undefined") return null
  return window.localStorage.getItem(`${TASK_MEETING_LINK_PREFIX}${taskId}`)
}

const WORKSTATION_MEETING_DRAFT_KEY = "sparkbot_workstation_roundtable_draft"
const WORKSTATION_MEETING_META_PREFIX = "sparkbot_workstation_meeting_room:"

export interface WorkstationMeetingDraft {
  seats: Array<string | null>
  roomId: string | null
  roomName: string
}

export interface WorkstationMeetingSeatMeta {
  seatIndex: number
  stationId: string
  label: string
  accentHex: string
  agentHandle?: string
  agentProvisioning?: "builtin" | "custom"
  agentProvider?: string
  agentDescription?: string
}

export interface WorkstationMeetingRoomMeta {
  roomId: string
  roomName: string
  launchedAt: string
  protocolLabel: string
  seats: WorkstationMeetingSeatMeta[]
}

export interface LaunchMeetingRoomOptions {
  roomName?: string
  seats: WorkstationMeetingSeatMeta[]
}

export function buildEmptyMeetingDraft(): WorkstationMeetingDraft {
  return {
    seats: new Array(ROUND_TABLE_SEAT_COUNT).fill(null),
    roomId: null,
    roomName: "Roundtable",
  }
}

export function normalizeMeetingSeats(
  seats: Array<string | null> | undefined,
): Array<string | null> {
  return new Array(ROUND_TABLE_SEAT_COUNT)
    .fill(null)
    .map((_, index) => seats?.[index] ?? null)
}

export function loadMeetingDraft(): WorkstationMeetingDraft {
  if (typeof window === "undefined") return buildEmptyMeetingDraft()

  try {
    const raw = window.localStorage.getItem(WORKSTATION_MEETING_DRAFT_KEY)
    if (!raw) return buildEmptyMeetingDraft()
    const parsed = JSON.parse(raw) as Partial<WorkstationMeetingDraft>
    return {
      seats: normalizeMeetingSeats(parsed.seats),
      roomId: null,
      roomName: parsed.roomName || "Roundtable",
    }
  } catch {
    return buildEmptyMeetingDraft()
  }
}

export function saveMeetingDraft(draft: WorkstationMeetingDraft): void {
  if (typeof window === "undefined") return
  window.localStorage.setItem(
    WORKSTATION_MEETING_DRAFT_KEY,
    JSON.stringify({
      seats: normalizeMeetingSeats(draft.seats),
      roomId: null,
      roomName: draft.roomName || "Roundtable",
    }),
  )
}

export function saveMeetingRoomMeta(meta: WorkstationMeetingRoomMeta): void {
  if (typeof window === "undefined") return
  window.localStorage.setItem(
    `${WORKSTATION_MEETING_META_PREFIX}${meta.roomId}`,
    JSON.stringify(meta),
  )
}

export function loadMeetingRoomMeta(roomId: string): WorkstationMeetingRoomMeta | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(`${WORKSTATION_MEETING_META_PREFIX}${roomId}`)
    if (!raw) return null
    return JSON.parse(raw) as WorkstationMeetingRoomMeta
  } catch {
    return null
  }
}

export function listMeetingRoomMetas(): WorkstationMeetingRoomMeta[] {
  if (typeof window === "undefined") return []
  const metas: WorkstationMeetingRoomMeta[] = []
  for (let i = 0; i < window.localStorage.length; i += 1) {
    const key = window.localStorage.key(i)
    if (!key || !key.startsWith(WORKSTATION_MEETING_META_PREFIX)) continue
    try {
      const raw = window.localStorage.getItem(key)
      if (!raw) continue
      metas.push(JSON.parse(raw) as WorkstationMeetingRoomMeta)
    } catch {
      continue
    }
  }
  return metas.sort((a, b) => Date.parse(b.launchedAt) - Date.parse(a.launchedAt))
}

export function deleteMeetingRoomMeta(roomId: string): void {
  if (typeof window === "undefined") return
  window.localStorage.removeItem(`${WORKSTATION_MEETING_META_PREFIX}${roomId}`)
}

export async function launchMeetingRoom({
  roomName = "Roundtable",
  seats,
}: LaunchMeetingRoomOptions): Promise<WorkstationMeetingRoomMeta> {
  await ensureMeetingSeatAgents(seats)
  const description = "Launched from Sparkbot Workstation. Autonomous meeting mode."
  const createRes = await apiFetch("/api/v1/chat/rooms/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ name: roomName, description }),
  })
  if (!createRes.ok) throw new Error("Could not create roundtable room.")

  const created = await createRes.json()
  const roomId = created.id as string
  if (!roomId) throw new Error("Roundtable room id missing after creation.")

  const patchRes = await apiFetch(`/api/v1/chat/rooms/${roomId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      name: roomName,
      description,
      meeting_mode_enabled: true,
      meeting_mode_bots_mention_only: true,
      meeting_mode_max_bot_msgs_per_min: 7,
      persona:
        "Roundtable mode. After the owner kickoff, the room works autonomously. One participant speaks at a time, but the handoff is automatic. Stop only when the issue is solved, blocked, looping, or when owner approval or missing input is needed.",
    }),
  })
  if (!patchRes.ok) {
    throw new Error("Could not prepare meeting room.")
  }

  const launchedAt = new Date()
  const participantLines = seats.map((seat) => `- Chair ${seat.seatIndex + 1}: ${seat.label}`).join("\n")

  await apiFetch(`/api/v1/chat/rooms/${roomId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      content: `Roundtable launched from Workstation.\n\nAutonomous meeting mode is on.\nThe owner can interrupt at any time, but the room should continue without waiting between turns.\n\nSeated participants:\n${participantLines}`,
    }),
  }).catch(() => {})

  const artifactMarkdown = [
    `# Roundtable Meeting — ${launchedAt.toISOString().replace("T", " ").slice(0, 16)} UTC`,
    "",
    "## Purpose",
    "_To be defined by participants._",
    "",
    "## Participants",
    ...seats.map((seat) => `- **Chair ${seat.seatIndex + 1}:** ${seat.label}`),
    "",
    "## Agenda",
    "- _To be defined._",
    "",
    "## Discussion",
    "_Meeting in progress._",
    "",
    "## Decisions",
    "- _None recorded yet._",
    "",
    "## Action Items",
    "- [ ] _None recorded yet._",
    "",
    "## Open Questions",
    "- _None recorded yet._",
    "",
    "## Next Steps",
    "- _To be determined._",
  ].join("\n")

  await apiFetch(`/api/v1/chat/rooms/${roomId}/artifacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      type: "notes",
      content_markdown: artifactMarkdown,
    }),
  }).catch(() => {})

  const meetingMeta: WorkstationMeetingRoomMeta = {
    roomId,
    roomName,
    launchedAt: launchedAt.toISOString(),
    protocolLabel: "Autonomous meeting",
    seats,
  }
  saveMeetingRoomMeta(meetingMeta)
  return meetingMeta
}

// ─── launchTaskMeeting ────────────────────────────────────────────────────────
// Like launchMeetingRoom but pre-seeded with a guardian task's context.

export interface GuardianTaskInfo {
  id: string
  name: string
  tool_name: string
  schedule: string
  last_status?: string | null
  last_message?: string | null
}

export async function launchTaskMeeting({
  task,
  seats,
}: {
  task: GuardianTaskInfo
  seats: WorkstationMeetingSeatMeta[]
}): Promise<WorkstationMeetingRoomMeta> {
  await ensureMeetingSeatAgents(seats)
  const roomName = `Project: ${task.name}`
  const description = `Workstation project meeting for task: ${task.name} (${task.tool_name})`

  const createRes = await apiFetch("/api/v1/chat/rooms/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ name: roomName, description }),
  })
  if (!createRes.ok) throw new Error("Could not create project meeting room.")

  const created = await createRes.json()
  const roomId = created.id as string
  if (!roomId) throw new Error("Project meeting room id missing after creation.")

  const statusNote = task.last_status
    ? `Last run: ${task.last_status}${task.last_message ? ` — ${task.last_message.slice(0, 120)}` : ""}`
    : "No runs yet."

  const patchRes = await apiFetch(`/api/v1/chat/rooms/${roomId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      name: roomName,
      description,
      meeting_mode_enabled: true,
      meeting_mode_bots_mention_only: true,
      meeting_mode_max_bot_msgs_per_min: 7,
      persona:
        "Project meeting mode. The team is working on a specific task. " +
        "After the owner defines the goal, participants work autonomously: one at a time, " +
        "no waiting between turns. Stop only when blocked, looped, or when owner input is needed.",
    }),
  })
  if (!patchRes.ok) throw new Error("Could not configure project meeting room.")

  const launchedAt = new Date()
  const participantLines = seats.map((s) => `- Chair ${s.seatIndex + 1}: ${s.label}`).join("\n")

  await apiFetch(`/api/v1/chat/rooms/${roomId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      content: [
        `Project meeting launched from Workstation.`,
        ``,
        `**Task:** ${task.name}`,
        `**Tool:** ${task.tool_name}`,
        `**Schedule:** ${task.schedule}`,
        `**Status:** ${statusNote}`,
        ``,
        `Autonomous meeting mode is on. Define your goal below to begin.`,
        ``,
        `Seated team:`,
        participantLines,
      ].join("\n"),
    }),
  }).catch(() => {})

  const artifactMarkdown = [
    `# Project Meeting — ${task.name}`,
    ``,
    `_Started: ${launchedAt.toISOString().replace("T", " ").slice(0, 16)} UTC_`,
    ``,
    `## Task`,
    `- **Name:** ${task.name}`,
    `- **Tool:** ${task.tool_name}`,
    `- **Schedule:** ${task.schedule}`,
    `- **Status:** ${statusNote}`,
    ``,
    `## Team`,
    ...seats.map((s) => `- **Chair ${s.seatIndex + 1}:** ${s.label}`),
    ``,
    `## Goal`,
    `_To be defined by owner._`,
    ``,
    `## Discussion`,
    `_Meeting in progress._`,
    ``,
    `## Decisions`,
    `- _None recorded yet._`,
    ``,
    `## Action Items`,
    `- [ ] _None recorded yet._`,
  ].join("\n")

  await apiFetch(`/api/v1/chat/rooms/${roomId}/artifacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ type: "notes", content_markdown: artifactMarkdown }),
  }).catch(() => {})

  const meetingMeta: WorkstationMeetingRoomMeta = {
    roomId,
    roomName,
    launchedAt: launchedAt.toISOString(),
    protocolLabel: "Project meeting",
    seats,
  }
  saveMeetingRoomMeta(meetingMeta)
  return meetingMeta
}

function buildCustomSeatSystemPrompt(seat: WorkstationMeetingSeatMeta): string {
  const provider = (seat.agentProvider || "configured provider").trim()
  const roleSummary = (seat.agentDescription || `${seat.label} contributes a distinct perspective in workstation meetings.`).trim()
  return [
    `You are ${seat.label}, a workstation meeting participant.`,
    `Your configured provider context is ${provider}.`,
    roleSummary,
    "In roundtable meetings, contribute one distinct perspective at a time.",
    "Avoid filler, avoid repeating prior points, and push the discussion toward a clear recommendation or next action.",
  ].join(" ")
}

async function ensureMeetingSeatAgents(seats: WorkstationMeetingSeatMeta[]): Promise<void> {
  for (const seat of seats) {
    if (seat.agentProvisioning !== "custom" || !seat.agentHandle) continue
    const response = await apiFetch("/api/v1/chat/agents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        name: seat.agentHandle,
        emoji: "🤖",
        description: `${seat.label} workstation invite desk`,
        system_prompt: buildCustomSeatSystemPrompt(seat),
      }),
    })
    if (!response.ok && response.status !== 409) {
      const detail = await response.json().catch(() => ({ detail: "Could not prepare meeting participant." }))
      throw new Error(String(detail.detail ?? "Could not prepare meeting participant."))
    }
  }
}
