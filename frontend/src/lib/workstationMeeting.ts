import { apiFetch } from "@/lib/apiBase"
import { fetchControlsConfig, providerForModel, type SparkbotControlsConfig } from "@/lib/sparkbotControls"

export const ROUND_TABLE_SEAT_COUNT = 8
const DEFAULT_MEETING_HEARTBEAT_SCHEDULE = "every:3600"

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
  modelId?: string
  route?: string
  inviteApiKey?: string
  inviteAuthMode?: "api_key" | "oauth" | "codex_sub"
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

function displayProviderName(providerId: string, config: SparkbotControlsConfig | null): string {
  return config?.providers.find((provider) => provider.id === providerId)?.label || providerId || "provider"
}

function displayModelName(modelId: string, config: SparkbotControlsConfig | null): string {
  return config?.model_labels?.[modelId] || modelId
}

function modelForSeat(
  seat: WorkstationMeetingSeatMeta,
  config: SparkbotControlsConfig | null,
): string {
  const handle = slugifyMeetingHandle(seat.agentHandle || seat.label || seat.stationId, seat.stationId)
  return (
    seat.modelId
    || config?.agent_overrides?.[handle]?.model
    || config?.default_selection?.model
    || config?.active_model
    || config?.stack?.primary
    || ""
  ).trim()
}

function providerReadyForSeat(
  seat: WorkstationMeetingSeatMeta,
  modelId: string,
  config: SparkbotControlsConfig | null,
): boolean {
  if (seat.inviteApiKey?.trim()) return true
  const providerId = providerForModel(modelId)
  const provider = config?.providers.find((item) => item.id === providerId)
  if (!provider) return false
  if (providerId === "ollama") {
    return provider.models_available === true || (provider.configured && provider.reachable === true)
  }
  return provider.configured || provider.models_available === true
}

export function buildAssignedProviderReadinessSummary(
  seats: WorkstationMeetingSeatMeta[],
  config: SparkbotControlsConfig | null,
): string {
  const assigned = seats.filter((seat) => seat.agentHandle || seat.modelId || seat.inviteApiKey)
  if (assigned.length === 0) return "Assigned provider check: no assigned model seats."
  const providers = new Set<string>()
  for (const seat of assigned) {
    const modelId = modelForSeat(seat, config)
    if (modelId) providers.add(displayProviderName(providerForModel(modelId), config))
  }
  const providerList = Array.from(providers).filter(Boolean).join(", ") || "default route"
  return `Assigned provider check: ${assigned.length} seat${assigned.length === 1 ? "" : "s"} ready (${providerList}).`
}

function assertAssignedProvidersReady(
  seats: WorkstationMeetingSeatMeta[],
  config: SparkbotControlsConfig | null,
): void {
  const missing: string[] = []
  for (const seat of seats) {
    const modelId = modelForSeat(seat, config)
    const seatLabel = `Seat ${seat.seatIndex + 1} ${seat.label}`.trim()
    if (!modelId) {
      missing.push(`${seatLabel}: no assigned or default model`)
      continue
    }
    if (!providerReadyForSeat(seat, modelId, config)) {
      const providerId = providerForModel(modelId)
      missing.push(`${seatLabel}: ${displayProviderName(providerId, config)} for ${displayModelName(modelId, config)}`)
    }
  }
  if (missing.length > 0) {
    throw new Error(`Meeting provider check failed: ${missing.join("; ")}. Configure only those assigned seats in Controls.`)
  }
}

function buildMeetingManifestMeta(
  roomName: string,
  protocolLabel: string,
  seats: WorkstationMeetingSeatMeta[],
) {
  return {
    source: "meeting_manifest",
    room_name: roomName,
    protocol_label: protocolLabel,
    heartbeat_schedule: DEFAULT_MEETING_HEARTBEAT_SCHEDULE,
    auto_heartbeat: true,
    participants: seats.map((seat) => ({
      seatIndex: seat.seatIndex,
      stationId: seat.stationId,
      label: seat.label,
      handle: slugifyMeetingHandle(seat.agentHandle || seat.label || seat.stationId, seat.stationId),
      modelId: seat.modelId || null,
      route: seat.route || null,
    })),
  }
}

async function persistMeetingManifest(
  roomId: string,
  roomName: string,
  protocolLabel: string,
  seats: WorkstationMeetingSeatMeta[],
): Promise<void> {
  const manifestMeta = buildMeetingManifestMeta(roomName, protocolLabel, seats)
  const response = await apiFetch(`/api/v1/chat/rooms/${roomId}/artifacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      type: "agenda",
      content_markdown: [
        `# Meeting Manifest — ${roomName}`,
        "",
        `Protocol: ${protocolLabel}`,
        `Heartbeat: ${DEFAULT_MEETING_HEARTBEAT_SCHEDULE}`,
        "",
        "## Participants",
        ...manifestMeta.participants.map((participant) => `- @${participant.handle} — ${participant.label}`),
      ].join("\n"),
      meta_json: manifestMeta,
    }),
  })
  if (!response.ok) {
    throw new Error("Could not persist meeting manifest.")
  }
}

async function ensureMeetingHeartbeatTask(roomId: string, roomName: string): Promise<void> {
  const response = await apiFetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      name: `${roomName} heartbeat`,
      tool_name: "meeting_heartbeat",
      schedule: DEFAULT_MEETING_HEARTBEAT_SCHEDULE,
      tool_args: {},
    }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: "Could not schedule meeting heartbeat." }))
    throw new Error(String(detail.detail ?? "Could not schedule meeting heartbeat."))
  }
}

export function slugifyMeetingHandle(value: string, fallback = "participant"): string {
  const normalized = (value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
  return normalized || fallback
}

function enrichMeetingSeats(
  seats: WorkstationMeetingSeatMeta[],
  stack?: {
    primary: string
    backup_1: string
    backup_2: string
    heavy_hitter: string
  },
): WorkstationMeetingSeatMeta[] {
  return seats.map((seat) => {
    const nextSeat = { ...seat }
    if (!nextSeat.agentHandle) {
      if (nextSeat.stationId === "sparkbot") nextSeat.agentHandle = "sparkbot"
      else if (nextSeat.stationId === "sb-researcher") nextSeat.agentHandle = "researcher"
      else if (nextSeat.stationId === "sb-coder") nextSeat.agentHandle = "coder"
      else if (nextSeat.stationId === "sb-analyst") nextSeat.agentHandle = "analyst"
      else nextSeat.agentHandle = slugifyMeetingHandle(nextSeat.label, nextSeat.stationId)
    }
    if (!nextSeat.modelId && stack) {
      if (nextSeat.stationId === "stack-backup_1") nextSeat.modelId = stack.backup_1 || undefined
      if (nextSeat.stationId === "stack-backup_2") nextSeat.modelId = stack.backup_2 || undefined
      if (nextSeat.stationId === "stack-heavy_hitter") nextSeat.modelId = stack.heavy_hitter || undefined
    }
    if (!nextSeat.route && nextSeat.modelId) {
      nextSeat.route = "default"
    }
    if (!nextSeat.agentProvisioning) {
      nextSeat.agentProvisioning =
        nextSeat.agentHandle && !["sparkbot", "researcher", "coder", "analyst"].includes(nextSeat.agentHandle)
          ? "custom"
          : "builtin"
    }
    return nextSeat
  })
}

export function getMeetingParticipantHandles(seats: WorkstationMeetingSeatMeta[]): string[] {
  return seats
    .map((seat) => slugifyMeetingHandle(seat.agentHandle || seat.label || seat.stationId, seat.stationId))
    .filter((handle, index, values): handle is string => Boolean(handle) && values.indexOf(handle) === index)
}

async function ensureMeetingAgentOverrides(seats: WorkstationMeetingSeatMeta[]): Promise<void> {
  const routedSeats = seats.filter((seat) => seat.agentHandle && seat.modelId)
  if (routedSeats.length === 0) return
  const config = await fetchControlsConfig()
  if (!config) return

  const nextOverrides = { ...(config.agent_overrides || {}) }
  let changed = false
  for (const seat of routedSeats) {
    const handle = slugifyMeetingHandle(seat.agentHandle || "", seat.stationId)
    const nextOverride = {
      route: seat.route || "default",
      model: seat.modelId,
    }
    const existing = nextOverrides[handle]
    if (existing?.route !== nextOverride.route || existing?.model !== nextOverride.model) {
      nextOverrides[handle] = nextOverride
      changed = true
    }
  }
  if (!changed) return

  const response = await apiFetch("/api/v1/chat/models/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ agent_overrides: nextOverrides }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: "Could not prepare meeting agent routing." }))
    throw new Error(String(detail.detail ?? "Could not prepare meeting agent routing."))
  }
}

export async function prepareMeetingSeats(seats: WorkstationMeetingSeatMeta[]): Promise<WorkstationMeetingSeatMeta[]> {
  const config = await fetchControlsConfig()
  const enrichedSeats = enrichMeetingSeats(seats, config?.stack)
  assertAssignedProvidersReady(enrichedSeats, config)
  await ensureMeetingSeatAgents(enrichedSeats)
  await ensureInviteAgentRoutes(enrichedSeats)
  await ensureMeetingAgentOverrides(enrichedSeats)
  return enrichedSeats
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
  const preparedSeats = await prepareMeetingSeats(seats)
  const readinessSummary = buildAssignedProviderReadinessSummary(preparedSeats, await fetchControlsConfig())
  const protocolLabel = "Autonomous meeting"
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
      meeting_mode_max_bot_msgs_per_min: 20,
      persona:
        "Roundtable mode. Seat 1 is the meeting manager. After the owner kickoff, run a chaired working session: first ideas from every participant, manager assessment, manager assignments, assigned work from every participant, manager summary, then plan, adjust, continue with another assignment/pass, or ask the owner for input. Do not discuss unrelated provider availability.",
    }),
  })
  if (!patchRes.ok) {
    throw new Error("Could not prepare meeting room.")
  }

  const launchedAt = new Date()
  const participantLines = preparedSeats.map((seat) => `- Chair ${seat.seatIndex + 1}: ${seat.label}`).join("\n")

  await apiFetch(`/api/v1/chat/rooms/${roomId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      content: `Roundtable launched from Workstation.\n\n${readinessSummary}\n\nSeat 1 is the meeting manager. After the owner kickoff, the room runs ideas, assessment, assignments, assigned work, summary, then either plans, adjusts, continues, or asks for owner input.\n\nSeated participants:\n${participantLines}`,
    }),
  }).catch(() => {})

  const artifactMarkdown = [
    `# Roundtable Meeting — ${launchedAt.toISOString().replace("T", " ").slice(0, 16)} UTC`,
    "",
    "## Purpose",
    "_To be defined by participants._",
    "",
    "## Participants",
    ...preparedSeats.map((seat) => `- **Chair ${seat.seatIndex + 1}:** ${seat.label}`),
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

  await persistMeetingManifest(roomId, roomName, protocolLabel, preparedSeats)
  await ensureMeetingHeartbeatTask(roomId, roomName)

  const meetingMeta: WorkstationMeetingRoomMeta = {
    roomId,
    roomName,
    launchedAt: launchedAt.toISOString(),
    protocolLabel,
    seats: preparedSeats,
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
  const preparedSeats = await prepareMeetingSeats(seats)
  const readinessSummary = buildAssignedProviderReadinessSummary(preparedSeats, await fetchControlsConfig())
  const roomName = `Project: ${task.name}`
  const protocolLabel = "Project meeting"
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
      meeting_mode_max_bot_msgs_per_min: 20,
      persona:
        "Project meeting mode. The team is working on a specific task. " +
        "Seat 1 is the meeting manager. After the owner defines the goal, run first ideas, " +
        "manager assessment, assignments, assigned work, manager summary, then plan, adjust, continue, or ask for owner input.",
    }),
  })
  if (!patchRes.ok) throw new Error("Could not configure project meeting room.")

  const launchedAt = new Date()
  const participantLines = preparedSeats.map((s) => `- Chair ${s.seatIndex + 1}: ${s.label}`).join("\n")

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
        readinessSummary,
        ``,
        `Seat 1 is the meeting manager. Define your goal below to begin the chaired meeting flow.`,
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
    ...preparedSeats.map((s) => `- **Chair ${s.seatIndex + 1}:** ${s.label}`),
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

  await persistMeetingManifest(roomId, roomName, protocolLabel, preparedSeats)
  await ensureMeetingHeartbeatTask(roomId, roomName)

  const meetingMeta: WorkstationMeetingRoomMeta = {
    roomId,
    roomName,
    launchedAt: launchedAt.toISOString(),
    protocolLabel,
    seats: preparedSeats,
  }
  saveMeetingRoomMeta(meetingMeta)
  return meetingMeta
}

function buildCustomSeatSystemPrompt(seat: WorkstationMeetingSeatMeta): string {
  const provider = (seat.agentProvider || "configured provider").trim()
  const modelLine = seat.modelId ? `Your assigned model is ${seat.modelId}.` : ""
  const roleSummary = (seat.agentDescription || `${seat.label} contributes a distinct perspective in workstation meetings.`).trim()
  return [
    `You are ${seat.label}, a workstation meeting participant.`,
    `Your configured provider context is ${provider}.`,
    modelLine,
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

async function ensureInviteAgentRoutes(seats: WorkstationMeetingSeatMeta[]): Promise<void> {
  for (const seat of seats) {
    if (seat.agentProvisioning !== "custom" || !seat.agentHandle) continue
    if (!seat.modelId && !seat.inviteApiKey) continue
    await apiFetch(`/api/v1/chat/agents/${encodeURIComponent(seat.agentHandle)}/invite-route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        model: seat.modelId || null,
        api_key: seat.inviteApiKey || null,
        auth_mode: seat.inviteAuthMode || null,
      }),
    }).catch(() => {})
  }
}
