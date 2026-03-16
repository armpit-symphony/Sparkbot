// Guardian Spine operator API client
// All endpoints require superuser authentication (cookie-first).

export interface SpineTask {
  task_id: string
  title: string
  status: string
  priority: string | null
  room_id: string | null
  project_id: string | null
  source_kind: string | null
  source_ref: string | null
  owner_kind: string | null
  owner_id: string | null
  approval_state: string | null
  confidence: number | null
  tags: string[]
  created_at: string
  updated_at: string
  // Additional backend fields
  summary: string | null
  type: string | null
  created_by_subsystem: string | null
  updated_by_subsystem: string | null
  approval_required: boolean
  parent_task_id: string | null
  depends_on: string[]
  last_progress_at: string | null
  closed_at: string | null
  chat_task_id: string | null
}

export interface SpineProject {
  project_id: string
  display_name: string
  slug: string
  status: string
  room_id: string | null
  owner_kind: string | null
  owner_id: string | null
  tags: string[]
  created_at: string | null
  updated_at: string
  summary: string | null
  source_kind: string | null
  source_ref: string | null
  created_by_subsystem: string | null
  updated_by_subsystem: string | null
  parent_project_id: string | null
}

export interface SpineEvent {
  event_id: string
  event_type: string
  occurred_at: string
  subsystem: string
  actor_kind: string | null
  actor_id: string | null
  source_kind: string | null
  source_ref: string | null
  correlation_id: string
  task_id: string | null
  project_id: string | null
  payload: Record<string, unknown> | null
}

export interface SpineProducer {
  subsystem: string
  description: string
  event_types: string[]
}

export interface SpineQueueResult {
  tasks: SpineTask[]
  count: number
}

export interface SpineProjectsResult {
  projects: SpineProject[]
  count: number
}

export interface SpineEventsResult {
  events: SpineEvent[]
  count: number
}

export interface SpineProjectWorkloadEntry {
  project_id: string
  display_name: string
  status: string
  total_tasks: number
  open_tasks: number
  blocked_tasks: number
  stale_tasks?: number
  approval_waiting_tasks?: number
  [key: string]: unknown
}

export interface SpineTMOverview {
  open_queue: SpineTask[]
  blocked_queue: SpineTask[]
  orphan_queue: SpineTask[]
  approval_waiting_queue: SpineTask[]
  stale_queue: SpineTask[]
  recently_resurfaced_queue: SpineTask[]
  assignment_ready_queue: SpineTask[]
  project_workload_summary: { projects: SpineProjectWorkloadEntry[]; count: number }
}

export interface SpineApproval {
  id: string
  task_id: string
  requester_id: string | null
  approver_id: string | null
  approval_method: string | null
  state: string
  scope: string[]
  expires_at: string | null
  created_at: string
  updated_at: string
}

export interface SpineHandoff {
  id: string
  task_id: string
  room_id: string
  summary: string
  created_at: string
  source_ref: string | null
}

export interface SpineTaskLineage {
  task: SpineTask
  parent: SpineTask | null
  children: SpineTask[]
  dependencies: SpineTask[]
  related: SpineTask[]
  approvals: SpineApproval[]
  handoffs: SpineHandoff[]
}

export type SpineQueueName =
  | "open"
  | "blocked"
  | "approval-waiting"
  | "stale"
  | "orphaned"
  | "missing-source"
  | "missing-project"
  | "resurfaced"
  | "executive-directives"

const SPINE_BASE = "/api/v1/chat/spine/operator"

async function spineGet<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(path, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString(), { credentials: "include" })
  if (!res.ok) {
    throw new Error(`Spine API error ${res.status}: ${url.pathname}`)
  }
  return res.json() as Promise<T>
}

export function fetchSpineTMOverview(limitPerQueue = 5): Promise<SpineTMOverview> {
  return spineGet<SpineTMOverview>(`${SPINE_BASE}/task-master/overview`, {
    limit_per_queue: limitPerQueue,
  })
}

export function fetchSpineQueue(queue: SpineQueueName, limit = 25): Promise<SpineQueueResult> {
  return spineGet<SpineQueueResult>(`${SPINE_BASE}/queues/${queue}`, { limit })
}

export function fetchSpineRecentEvents(limit = 25): Promise<SpineEventsResult> {
  return spineGet<SpineEventsResult>(`${SPINE_BASE}/events/recent`, { limit })
}

export function fetchSpineProjects(limit = 50): Promise<SpineProjectsResult> {
  return spineGet<SpineProjectsResult>(`${SPINE_BASE}/projects`, { limit })
}

export function fetchSpineProjectWorkload(): Promise<{ projects: SpineProjectWorkloadEntry[]; count: number }> {
  return spineGet<{ projects: SpineProjectWorkloadEntry[]; count: number }>(`${SPINE_BASE}/projects/workload`)
}

export function fetchSpineProducers(): Promise<{ producers: SpineProducer[]; count: number }> {
  return spineGet<{ producers: SpineProducer[]; count: number }>(`${SPINE_BASE}/producers`)
}

export function fetchSpineTaskDetail(taskId: string): Promise<SpineTaskLineage> {
  return spineGet<SpineTaskLineage>(`${SPINE_BASE}/tasks/${taskId}/detail`)
}

// ── Guardian operator API helpers ─────────────────────────────────────────────

const GUARDIAN_BASE = "/api/v1/chat/guardian"

async function guardianFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init })
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new Error(`Guardian API ${res.status}: ${text || path}`)
  }
  return res.json() as Promise<T>
}

export interface BreakglassStatus {
  active: boolean
  session_id?: string
  ttl_remaining?: number
  scopes?: string[]
}

export interface VaultEntry {
  alias: string
  category: string
  access_policy: string
  notes: string | null
  created_at: string
  updated_at: string
  last_used_at: string | null
  rotation_due: string | null
}

export interface GuardianStatus {
  breakglass: { active: boolean; ttl_remaining: number | null }
  operator: { username: string; usernames_configured: boolean; open_mode: boolean }
  pin_configured: boolean
  vault_configured: boolean
  memory_guardian_enabled: boolean
  task_guardian_enabled: boolean
  task_guardian_write_enabled: boolean
}

export function fetchBreakglassStatus(): Promise<BreakglassStatus> {
  return guardianFetch<BreakglassStatus>(`${GUARDIAN_BASE}/breakglass/status`)
}

export function activateBreakglass(pin: string): Promise<BreakglassStatus> {
  return guardianFetch<BreakglassStatus>(`${GUARDIAN_BASE}/breakglass`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pin }),
  })
}

export function deactivateBreakglass(): Promise<{ closed: boolean }> {
  return guardianFetch<{ closed: boolean }>(`${GUARDIAN_BASE}/breakglass`, { method: "DELETE" })
}

export function fetchVaultList(): Promise<{ items: VaultEntry[]; count: number }> {
  return guardianFetch<{ items: VaultEntry[]; count: number }>(`${GUARDIAN_BASE}/vault`)
}

export function addVaultSecret(
  alias: string,
  value: string,
  policy: string,
  category = "general",
  notes?: string,
): Promise<VaultEntry> {
  return guardianFetch<VaultEntry>(`${GUARDIAN_BASE}/vault`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ alias, value, access_policy: policy, category, notes }),
  })
}

export function deleteVaultSecret(alias: string): Promise<{ deleted: boolean; alias: string }> {
  return guardianFetch<{ deleted: boolean; alias: string }>(`${GUARDIAN_BASE}/vault/${encodeURIComponent(alias)}`, {
    method: "DELETE",
  })
}

export function fetchGuardianStatus(): Promise<GuardianStatus> {
  return guardianFetch<GuardianStatus>(`${GUARDIAN_BASE}/status`)
}

export function setTaskGuardianWriteMode(enabled: boolean): Promise<{ write_enabled: boolean }> {
  return guardianFetch<{ write_enabled: boolean }>(`${GUARDIAN_BASE}/tasks/write-mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  })
}

// ── Project management API helpers ────────────────────────────────────────────

const ROOMS_BASE = "/api/v1/chat/rooms"

async function roomsFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init })
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new Error(`Projects API ${res.status}: ${text || path}`)
  }
  return res.json() as Promise<T>
}

export function createProject(
  roomId: string,
  data: { display_name: string; summary?: string; status?: string; tags?: string[] },
): Promise<SpineProject> {
  return roomsFetch<SpineProject>(`${ROOMS_BASE}/${roomId}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  })
}

export function updateProject(
  roomId: string,
  projectId: string,
  data: {
    display_name?: string
    summary?: string
    tags?: string[]
    new_status?: string
    reason?: string
    owner_kind?: string
    owner_id?: string
  },
): Promise<SpineProject> {
  return roomsFetch<SpineProject>(`${ROOMS_BASE}/${roomId}/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  })
}

export function archiveProject(
  roomId: string,
  projectId: string,
  force = false,
): Promise<{ archived: boolean; project_id: string }> {
  return roomsFetch(`${ROOMS_BASE}/${roomId}/projects/${projectId}?force=${force}`, { method: "DELETE" })
}

export function attachTaskToProject(
  roomId: string,
  projectId: string,
  taskId: string,
): Promise<Record<string, unknown>> {
  return roomsFetch(`${ROOMS_BASE}/${roomId}/projects/${projectId}/tasks/${taskId}`, { method: "POST" })
}

export function detachTaskFromProject(
  roomId: string,
  projectId: string,
  taskId: string,
): Promise<Record<string, unknown>> {
  return roomsFetch(`${ROOMS_BASE}/${roomId}/projects/${projectId}/tasks/${taskId}`, { method: "DELETE" })
}
