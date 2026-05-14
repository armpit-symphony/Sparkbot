import { useEffect, useMemo, useState } from "react"
import {
  Activity,
  ClipboardList,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  Route,
  ShieldCheck,
  Shield,
  UserRoundCog,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiFetch } from "@/lib/apiBase"
import { fetchControlsConfig, type SparkbotControlsConfig } from "@/lib/sparkbotControls"
import { fetchGuardianStatus, setTaskGuardianWriteMode, type GuardianStatus } from "@/lib/spine"

interface RoomInfo {
  id: string
  name: string
  execution_allowed: boolean
  persona?: string
}

interface GuardianTaskRecord {
  id: string
  name: string
  tool_name: string
  schedule: string
  enabled: boolean
  next_run_at?: string | null
  last_status?: string | null
  last_message?: string | null
}

interface GuardianRunRecord {
  run_id: string
  task_id: string
  status: string
  message?: string | null
  created_at: string
}

interface DashboardSummary {
  summary?: {
    pending_approvals?: number
    guardian_jobs?: number
    guardian_jobs_enabled?: number
    task_guardian_enabled?: boolean
    token_guardian_mode?: string
  }
  today?: {
    token_guardian?: {
      mode?: string
      live_ready?: boolean
      configured_models?: string[]
      allowed_live_models?: string[]
      total_tokens?: number
      total_cost?: number
      requests?: number
      live_routes_24h?: number
      suggested_switches_24h?: number
      estimated_savings_24h?: number
      top_models?: Array<{ model: string; tokens: number }>
      last_route?: {
        created_at?: string
        classification?: string | null
        current_model?: string | null
        selected_model?: string | null
        applied_model?: string | null
        fallback_reason?: string | null
      } | null
    }
  }
}

interface HealthCheck {
  message?: string
  status?: string
}

interface SecurityStatus {
  operator: {
    mode: "open" | "explicit"
    username?: string
    usernames: string[]
    pin_configured: boolean
    breakglass_active: boolean
    breakglass_ttl_remaining: number
  }
  passphrase: {
    configured: boolean
    length: number
    weak_default: boolean
    score: number
    label: "weak" | "fair" | "strong"
  }
  features: Record<string, { env_key: string; enabled: boolean }>
  cors: { origins: string[]; has_wildcard: boolean }
  exposure: {
    frontend_bind_host: string
    frontend_port: string
    frontend_public: boolean
    backend_bind: string
  }
  env_files: Array<{
    path: string
    exists: boolean
    manageable: boolean
    mode?: string
    secure?: boolean
    error?: string
  }>
  frontend_headers: {
    checked: boolean
    ok: boolean
    url?: string
    present: string[]
    missing: string[]
    note?: string
  }
  provider_secrets: Array<{
    provider: string
    env_key: string
    configured_in_env: boolean
    masked: string
    vault_alias: string
    configured_in_vault: boolean
  }>
  security_modes: Array<{ id: string; label: string; description: string }>
  operator_guidance: Array<{ area: string; operator_action: string }>
}

type TokenGuardianSummary = NonNullable<NonNullable<DashboardSummary["today"]>["token_guardian"]>

interface CommandCenterOperationsProps {
  refreshNonce: number
  onRefresh: () => void
}

const TASK_TOOL_OPTIONS = [
  "health_check",
  "memory_retrieval_stats",
  "memory_reindex",
  "email_digest",
  "telegram_send",
  "github_create_issue",
]

function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const diff = Date.now() - date.getTime()
  const seconds = Math.max(0, Math.floor(diff / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

async function readJson<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const response = await apiFetch(path, { credentials: "include", ...init })
    if (!response.ok) return null
    return (await response.json()) as T
  } catch {
    return null
  }
}

async function loadRoom(): Promise<RoomInfo | null> {
  const bootstrap = await readJson<{ room_id: string }>("/api/v1/chat/users/bootstrap", {
    method: "POST",
  })
  if (!bootstrap?.room_id) return null
  return readJson<RoomInfo>(`/api/v1/chat/rooms/${bootstrap.room_id}`)
}

export function CommandCenterOperations({ refreshNonce, onRefresh }: CommandCenterOperationsProps) {
  const [room, setRoom] = useState<RoomInfo | null>(null)
  const [personaDraft, setPersonaDraft] = useState("")
  const [customGuardrailsDraft, setCustomGuardrailsDraft] = useState("")
  const [config, setConfig] = useState<SparkbotControlsConfig | null>(null)
  const [guardianStatus, setGuardianStatus] = useState<GuardianStatus | null>(null)
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null)
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null)
  const [health, setHealth] = useState<HealthCheck | null>(null)
  const [tasks, setTasks] = useState<GuardianTaskRecord[]>([])
  const [runs, setRuns] = useState<GuardianRunRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    let alive = true

    async function load() {
      setLoading(true)
      setError("")
      const [roomResult, configResult, guardianResult, securityResult, dashboardResult, healthResult] = await Promise.all([
        loadRoom(),
        fetchControlsConfig(),
        fetchGuardianStatus().catch(() => null),
        readJson<SecurityStatus>("/api/v1/chat/security/status"),
        readJson<DashboardSummary>("/api/v1/chat/dashboard/summary"),
        readJson<HealthCheck>("/api/v1/utils/health-check/"),
      ])

      if (!alive) return
      setRoom(roomResult)
      setPersonaDraft(roomResult?.persona ?? "")
      setCustomGuardrailsDraft(configResult?.custom_guardrails ?? "")
      setConfig(configResult)
      setGuardianStatus(guardianResult)
      setSecurityStatus(securityResult)
      setDashboard(dashboardResult)
      setHealth(healthResult)

      if (roomResult?.id) {
        const [tasksResult, runsResult] = await Promise.all([
          readJson<{ items?: GuardianTaskRecord[] }>(`/api/v1/chat/rooms/${roomResult.id}/guardian/tasks?limit=20`),
          readJson<{ items?: GuardianRunRecord[] }>(`/api/v1/chat/rooms/${roomResult.id}/guardian/runs?limit=10`),
        ])
        if (!alive) return
        setTasks(tasksResult?.items ?? [])
        setRuns(runsResult?.items ?? [])
      } else {
        setTasks([])
        setRuns([])
      }
      setLoading(false)
    }

    load().catch((err: unknown) => {
      if (!alive) return
      setError(err instanceof Error ? err.message : "Command Center data could not be loaded.")
      setLoading(false)
    })

    return () => {
      alive = false
    }
  }, [refreshNonce])

  const readyProviders = config?.providers?.filter(
    (provider) => provider.configured || provider.models_available === true,
  ).length ?? 0
  const securityGuardrailsActive = Boolean(config?.security_guardrails_enabled ?? guardianStatus?.security_guardrails_enabled)
  const tokenGuardian = dashboard?.today?.token_guardian
  const tokenMode = config?.token_guardian_mode ?? dashboard?.summary?.token_guardian_mode ?? tokenGuardian?.mode ?? "off"
  const enabledTasks = useMemo(() => tasks.filter((task) => task.enabled).length, [tasks])

  async function reloadWithStatus(text: string) {
    setMessage(text)
    onRefresh()
  }

  async function savePersona() {
    if (!room) return
    setMessage("")
    setError("")
    const response = await apiFetch(`/api/v1/chat/rooms/${room.id}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ persona: personaDraft }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? "Room persona could not be saved.")
      return
    }
    await reloadWithStatus("Room persona saved.")
  }

  async function saveTokenMode(nextMode: string) {
    setMessage("")
    setError("")
    const response = await apiFetch("/api/v1/chat/models/config", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token_guardian_mode: nextMode }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? "Token Guardian mode could not be saved.")
      return
    }
    await reloadWithStatus(`Token Guardian set to ${nextMode}.`)
  }

  async function toggleSecurityGuardrails() {
    const next = !securityGuardrailsActive
    setMessage("")
    setError("")
    const response = await apiFetch("/api/v1/chat/models/config", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ security_guardrails_enabled: next }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? "Security guardrails could not be updated.")
      return
    }
    const data = await response.json().catch(() => null)
    if (data) {
      setConfig(data as SparkbotControlsConfig)
      setCustomGuardrailsDraft((data as SparkbotControlsConfig).custom_guardrails ?? customGuardrailsDraft)
    }
    await reloadWithStatus(next ? "Security guardrails enabled." : "Security guardrails disabled.")
  }

  async function saveCustomGuardrails() {
    setMessage("")
    setError("")
    const response = await apiFetch("/api/v1/chat/models/config", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ custom_guardrails: customGuardrailsDraft }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? "Custom guardrails could not be saved.")
      return
    }
    const data = await response.json().catch(() => null)
    if (data) {
      setConfig(data as SparkbotControlsConfig)
      setCustomGuardrailsDraft((data as SparkbotControlsConfig).custom_guardrails ?? customGuardrailsDraft)
    }
    await reloadWithStatus("Custom Security guardrails saved.")
  }

  async function setPin(currentPin: string, pin: string, pinConfirm: string) {
    setMessage("")
    setError("")
    const response = await apiFetch("/api/v1/chat/security/operator-pin", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_pin: currentPin || null, pin, pin_confirm: pinConfirm }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? "Operator PIN could not be saved.")
      return
    }
    await reloadWithStatus("Operator PIN saved.")
  }

  async function rotatePassphrase(passphrase: string) {
    setMessage("")
    setError("")
    const response = await apiFetch("/api/v1/chat/security/passphrase", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passphrase }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? "Sparkbot passphrase could not be rotated.")
      return false
    }
    await reloadWithStatus("Sparkbot passphrase rotated.")
    return true
  }

  async function saveOperatorUsers(usernames: string[]) {
    setMessage("")
    setError("")
    const response = await apiFetch("/api/v1/chat/security/operator-users", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usernames }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? "Operator usernames could not be saved.")
      return false
    }
    await reloadWithStatus("Operator usernames saved.")
    return true
  }

  async function fixEnvPermissions() {
    setMessage("")
    setError("")
    const response = await apiFetch("/api/v1/chat/security/fix-permissions", {
      method: "POST",
      credentials: "include",
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? ".env permissions could not be fixed.")
      return
    }
    await reloadWithStatus(".env permissions fixed where Sparkbot can manage them.")
  }

  async function setTaskEnabled(taskId: string, enabled: boolean) {
    if (!room) return
    const response = await apiFetch(`/api/v1/chat/rooms/${room.id}/guardian/tasks/${taskId}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? "Task Guardian job could not be updated.")
      return
    }
    await reloadWithStatus(enabled ? "Task Guardian job resumed." : "Task Guardian job paused.")
  }

  async function createTask(input: { name: string; toolName: string; schedule: string; args: string }) {
    if (!room) return
    let parsedArgs: Record<string, unknown>
    try {
      parsedArgs = input.args.trim() ? JSON.parse(input.args) as Record<string, unknown> : {}
    } catch {
      setError("Task arguments must be valid JSON.")
      return
    }

    const response = await apiFetch(`/api/v1/chat/rooms/${room.id}/guardian/tasks`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: input.name,
        tool_name: input.toolName,
        schedule: input.schedule,
        args: parsedArgs,
      }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? "Task Guardian job could not be created.")
      return
    }
    await reloadWithStatus("Task Guardian job created.")
  }

  async function runTask(taskId: string) {
    if (!room) return
    const response = await apiFetch(`/api/v1/chat/rooms/${room.id}/guardian/tasks/${taskId}/run`, {
      method: "POST",
      credentials: "include",
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      setError(data?.detail ?? "Task Guardian job could not be run.")
      return
    }
    await reloadWithStatus("Task Guardian run completed.")
  }

  async function toggleTaskWriteMode() {
    if (!guardianStatus) return
    const next = !guardianStatus.task_guardian_write_enabled
    try {
      const result = await setTaskGuardianWriteMode(next)
      setGuardianStatus({ ...guardianStatus, task_guardian_write_enabled: result.write_enabled })
      setMessage(result.write_enabled ? "Task Guardian write mode enabled." : "Task Guardian write mode disabled.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task Guardian write mode could not be updated.")
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-xl border px-4 py-6 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" />
        Loading operational controls...
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {message ? (
        <div className="rounded-xl border border-blue-500/30 bg-blue-500/10 px-4 py-2 text-sm text-blue-700 dark:text-blue-300">
          {message}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <RoomPersonaCard room={room} personaDraft={personaDraft} onPersonaDraftChange={setPersonaDraft} onSave={savePersona} />

      <div className="grid gap-4 lg:grid-cols-3">
        <SystemHealthCard
          health={health}
          guardianStatus={guardianStatus}
          readyProviders={readyProviders}
          defaultModel={config?.default_selection?.label ?? config?.default_selection?.model ?? config?.active_model}
          pendingApprovals={dashboard?.summary?.pending_approvals ?? 0}
          onRefresh={onRefresh}
        />
        <TokenGuardianCard
          mode={tokenMode}
          tokenGuardian={tokenGuardian}
          onSaveMode={saveTokenMode}
        />
        <SecurityCard
          active={securityGuardrailsActive}
          customGuardrails={customGuardrailsDraft}
          securityStatus={securityStatus}
          onCustomGuardrailsChange={setCustomGuardrailsDraft}
          onSaveCustomGuardrails={saveCustomGuardrails}
          room={room}
          guardianStatus={guardianStatus}
          onToggle={toggleSecurityGuardrails}
          onSetPin={setPin}
          onRotatePassphrase={rotatePassphrase}
          onSaveOperatorUsers={saveOperatorUsers}
          onFixEnvPermissions={fixEnvPermissions}
        />
      </div>

      <TaskGuardianCard
        guardianStatus={guardianStatus}
        tasks={tasks}
        runs={runs}
        enabledTasks={enabledTasks}
        room={room}
        onToggleWriteMode={toggleTaskWriteMode}
        onCreateTask={createTask}
        onRunTask={runTask}
        onSetTaskEnabled={setTaskEnabled}
      />
    </div>
  )
}

function RoomPersonaCard({
  room,
  personaDraft,
  onPersonaDraftChange,
  onSave,
}: {
  room: RoomInfo | null
  personaDraft: string
  onPersonaDraftChange: (value: string) => void
  onSave: () => void
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <UserRoundCog className="size-4" />
          Room Persona
        </CardTitle>
        <CardDescription>
          Active room context for Sparkbot chat, Workstation, and safe-control workflows.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="outline">{room?.name ?? "No room context"}</Badge>
          <span className="text-muted-foreground">
            {room ? "Persona is applied through the existing room setting." : "Bootstrap a Sparkbot room to edit persona."}
          </span>
        </div>
        <textarea
          value={personaDraft}
          onChange={(event) => onPersonaDraftChange(event.target.value)}
          placeholder='e.g. "Keep replies concise and focus on operator-ready next actions."'
          rows={3}
          maxLength={500}
          className="w-full resize-none rounded-md border bg-muted/30 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring/30"
          disabled={!room}
        />
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">{personaDraft.length}/500</span>
          <Button size="sm" onClick={onSave} disabled={!room}>
            Save persona
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function SystemHealthCard({
  health,
  guardianStatus,
  readyProviders,
  defaultModel,
  pendingApprovals,
  onRefresh,
}: {
  health: HealthCheck | null
  guardianStatus: GuardianStatus | null
  readyProviders: number
  defaultModel?: string
  pendingApprovals: number
  onRefresh: () => void
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="size-4" />
              System Health
            </CardTitle>
            <CardDescription>Sparkbot API, model paths, and Guardian state.</CardDescription>
          </div>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={onRefresh}>
            <RefreshCw className="size-3.5" />
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <HealthRow label="API" value={health?.message ?? health?.status ?? "unavailable"} good={Boolean(health)} />
        <HealthRow label="Model paths" value={`${readyProviders} provider path${readyProviders === 1 ? "" : "s"}`} good={readyProviders > 0} />
        <HealthRow label="Default model" value={defaultModel ?? "not selected"} good={Boolean(defaultModel)} />
        <HealthRow label="Guardian" value={guardianStatus?.task_guardian_enabled ? "enabled" : "read-only or unavailable"} good={Boolean(guardianStatus?.task_guardian_enabled)} />
        <HealthRow label="Approvals" value={`${pendingApprovals} pending`} good={pendingApprovals === 0} />
      </CardContent>
    </Card>
  )
}

function HealthRow({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={good ? "text-xs font-medium text-blue-600 dark:text-blue-400" : "text-xs font-medium text-amber-600 dark:text-amber-400"}>
        {value}
      </span>
    </div>
  )
}

function TokenGuardianCard({
  mode,
  tokenGuardian,
  onSaveMode,
}: {
  mode: string
  tokenGuardian: TokenGuardianSummary | undefined
  onSaveMode: (mode: string) => void
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Route className="size-4" />
          Token Guardian
        </CardTitle>
        <CardDescription>Existing model-routing mode and usage summary.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <label className="text-xs font-medium text-muted-foreground" htmlFor="command-center-token-mode">
            Routing mode
          </label>
          <div className="mt-1 flex gap-2">
            <select
              id="command-center-token-mode"
              value={mode}
              onChange={(event) => onSaveMode(event.target.value)}
              className="min-w-0 flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none"
            >
              <option value="off">Off</option>
              <option value="shadow">Shadow</option>
              <option value="live">Live</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <Metric label="Requests" value={String(tokenGuardian?.requests ?? 0)} />
          <Metric label="Tokens" value={(tokenGuardian?.total_tokens ?? 0).toLocaleString()} />
          <Metric label="Live routes" value={String(tokenGuardian?.live_routes_24h ?? 0)} />
          <Metric label="Suggestions" value={String(tokenGuardian?.suggested_switches_24h ?? 0)} />
        </div>
        <div className="rounded-lg border px-3 py-2 text-xs text-muted-foreground">
          {tokenGuardian?.last_route ? (
            <>
              Last route: {tokenGuardian.last_route.current_model ?? "unknown"} to{" "}
              <span className="font-medium text-foreground">{tokenGuardian.last_route.applied_model ?? "unknown"}</span>,{" "}
              {formatRelativeTime(tokenGuardian.last_route.created_at)}
            </>
          ) : (
            "No Token Guardian route has been recorded yet."
          )}
        </div>
        {!tokenGuardian?.live_ready ? (
          <div className="rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
            Live routing is not configured; shadow mode can still record recommendations.
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-semibold tabular-nums">{value}</div>
    </div>
  )
}

function SecurityCard({
  active,
  customGuardrails,
  securityStatus,
  onCustomGuardrailsChange,
  onSaveCustomGuardrails,
  room,
  guardianStatus,
  onToggle,
  onSetPin,
  onRotatePassphrase,
  onSaveOperatorUsers,
  onFixEnvPermissions,
}: {
  active: boolean
  customGuardrails: string
  securityStatus: SecurityStatus | null
  onCustomGuardrailsChange: (value: string) => void
  onSaveCustomGuardrails: () => void
  room: RoomInfo | null
  guardianStatus: GuardianStatus | null
  onToggle: () => void
  onSetPin: (currentPin: string, pin: string, pinConfirm: string) => void
  onRotatePassphrase: (passphrase: string) => Promise<boolean>
  onSaveOperatorUsers: (usernames: string[]) => Promise<boolean>
  onFixEnvPermissions: () => void
}) {
  const [currentPin, setCurrentPin] = useState("")
  const [pin, setPin] = useState("")
  const [pinConfirm, setPinConfirm] = useState("")
  const [passphraseDraft, setPassphraseDraft] = useState("")
  const [operatorsDraft, setOperatorsDraft] = useState("")
  const pinConfigured = Boolean(securityStatus?.operator.pin_configured ?? guardianStatus?.pin_configured)
  const breakglassActive = Boolean(securityStatus?.operator.breakglass_active ?? guardianStatus?.breakglass.active)
  const canSavePin = /^\d{6}$/.test(pin) && pin === pinConfirm && (!pinConfigured || currentPin.length === 6)
  const insecureEnvFiles = securityStatus?.env_files.filter((file) => file.exists && file.secure === false) ?? []
  const enabledRiskyFeatures = Object.entries(securityStatus?.features ?? {}).filter(([, feature]) => feature.enabled)
  const providerEnvKeys = securityStatus?.provider_secrets.filter((secret) => secret.configured_in_env) ?? []

  useEffect(() => {
    if (securityStatus) {
      setOperatorsDraft(securityStatus.operator.usernames.join(", "))
    }
  }, [securityStatus])

  const operatorUsernames = operatorsDraft
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Shield className="size-4" />
          Security
        </CardTitle>
        <CardDescription>Backend-enforced posture, guardrails, and operator controls.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 text-xs sm:grid-cols-2">
          <StatusPill
            label="Passphrase"
            value={securityStatus?.passphrase.label ?? "unknown"}
            good={securityStatus?.passphrase.label === "strong"}
          />
          <StatusPill
            label="Operators"
            value={
              securityStatus
                ? securityStatus.operator.mode === "explicit"
                  ? `${securityStatus.operator.usernames.length} explicit`
                  : "open to humans"
                : "unavailable"
            }
            good={securityStatus?.operator.mode === "explicit"}
          />
          <StatusPill
            label="Frontend"
            value={securityStatus ? securityStatus.exposure.frontend_public ? "public bind" : "local bind" : "unavailable"}
            good={Boolean(securityStatus && !securityStatus.exposure.frontend_public)}
          />
          <StatusPill
            label="Headers"
            value={securityStatus?.frontend_headers.ok ? "present" : "missing"}
            good={Boolean(securityStatus?.frontend_headers.ok)}
          />
          <StatusPill
            label="CORS"
            value={securityStatus ? securityStatus.cors.has_wildcard ? "wildcard" : `${securityStatus.cors.origins.length} origins` : "unavailable"}
            good={Boolean(securityStatus && !securityStatus.cors.has_wildcard)}
          />
          <StatusPill
            label=".env files"
            value={insecureEnvFiles.length ? `${insecureEnvFiles.length} loose` : "600 or missing"}
            good={insecureEnvFiles.length === 0}
          />
        </div>
        <div className={`rounded-lg border px-3 py-3 ${active ? "border-blue-500/30 bg-blue-500/10" : "bg-muted/20"}`}>
          <div className="flex items-center justify-between gap-3">
            <label className="flex min-w-0 items-start gap-3">
              <input
                type="checkbox"
                checked={active}
                onChange={() => onToggle()}
                className="mt-0.5 h-4 w-4"
              />
              <div>
              <div className="text-sm font-semibold">Security {active ? "on" : "off"}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {active
                  ? "Strict Security guardrails, PIN prompts, service allowlists, and custom blockers are active."
                  : "Default owner mode: routine actions run; writes, deletes, sends, and service changes still ask yes/no."}
              </div>
              </div>
            </label>
            <Button size="sm" variant={active ? "outline" : "default"} onClick={onToggle}>
              {active ? "Turn off" : "Turn on"}
            </Button>
          </div>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="mb-2 flex items-center justify-between gap-2 text-xs font-semibold text-muted-foreground">
            <span>Custom blockers</span>
            <span>{customGuardrails.length}/4000</span>
          </div>
          <textarea
            value={customGuardrails}
            onChange={(event) => onCustomGuardrailsChange(event.target.value.slice(0, 4000))}
            placeholder={"One rule per line. Examples:\ntool:gmail_send\nregex:rm\\s+-rf\nkalshi-live-trading"}
            rows={4}
            className="w-full resize-none rounded-md border bg-background px-3 py-2 font-mono text-xs"
          />
          <div className="mt-2 flex justify-end">
            <Button size="sm" variant="outline" onClick={onSaveCustomGuardrails}>
              Save guardrails
            </Button>
          </div>
        </div>
        <div className="grid gap-2 text-xs">
          <StatusPill
            label="Room execution"
            value={!active ? "not enforced" : room?.execution_allowed ? "enabled" : "gated"}
            good={active ? Boolean(room?.execution_allowed) : true}
          />
          <StatusPill label="Operator PIN" value={pinConfigured ? "configured" : "required"} good={pinConfigured} />
          <StatusPill label="Break-glass" value={breakglassActive ? "active" : "inactive"} good={breakglassActive} />
        </div>
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
            <KeyRound className="size-3.5" />
            Rotate Sparkbot passphrase
          </div>
          <input
            type="password"
            value={passphraseDraft}
            onChange={(event) => setPassphraseDraft(event.target.value)}
            placeholder="New passphrase, 16+ characters"
            className="w-full rounded-md border bg-background px-3 py-2 text-xs"
            autoComplete="new-password"
          />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              Write action requires active break-glass. Stored value is never shown here.
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={!breakglassActive || passphraseDraft.trim().length < 16}
              onClick={async () => {
                const saved = await onRotatePassphrase(passphraseDraft.trim())
                if (saved) setPassphraseDraft("")
              }}
            >
              Rotate
            </Button>
          </div>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="mb-2 text-xs font-semibold text-muted-foreground">Explicit operator usernames</div>
          <textarea
            value={operatorsDraft}
            onChange={(event) => setOperatorsDraft(event.target.value)}
            placeholder="username1, username2"
            rows={2}
            className="w-full resize-none rounded-md border bg-background px-3 py-2 text-xs"
          />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              Include your current username before saving or the backend rejects the change.
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={!breakglassActive || operatorUsernames.length === 0}
              onClick={() => onSaveOperatorUsers(operatorUsernames)}
            >
              Save operators
            </Button>
          </div>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
            <KeyRound className="size-3.5" />
            {pinConfigured ? "Change operator PIN" : "Set operator PIN"}
          </div>
          {pinConfigured ? (
            <input
              type="password"
              inputMode="numeric"
              maxLength={6}
              value={currentPin}
              onChange={(event) => setCurrentPin(event.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="Current PIN"
              className="mb-2 w-full rounded-md border bg-background px-3 py-2 text-xs"
            />
          ) : null}
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              type="password"
              inputMode="numeric"
              maxLength={6}
              value={pin}
              onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder={pinConfigured ? "New PIN" : "New 6-digit PIN"}
              className="rounded-md border bg-background px-3 py-2 text-xs"
            />
            <input
              type="password"
              inputMode="numeric"
              maxLength={6}
              value={pinConfirm}
              onChange={(event) => setPinConfirm(event.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="Verify PIN"
              className="rounded-md border bg-background px-3 py-2 text-xs"
            />
          </div>
          <Button
            size="sm"
            variant="outline"
            className="mt-2"
            disabled={!canSavePin}
            onClick={() => {
              onSetPin(currentPin, pin, pinConfirm)
              setCurrentPin("")
              setPin("")
              setPinConfirm("")
            }}
          >
            Save PIN
          </Button>
        </div>
        <div className="rounded-lg border bg-muted/20 p-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="font-semibold text-foreground">Managed .env permissions</div>
              <div className="mt-1 text-muted-foreground">
                {insecureEnvFiles.length
                  ? insecureEnvFiles.map((file) => `${file.path} (${file.mode ?? "unknown"})`).join(", ")
                  : "No loose managed .env permissions detected."}
              </div>
            </div>
            <Button size="sm" variant="outline" disabled={!breakglassActive} onClick={onFixEnvPermissions}>
              Fix permissions
            </Button>
          </div>
        </div>
        <div className="grid gap-2 text-xs">
          <div className="rounded-lg border px-3 py-2">
            <div className="font-semibold text-foreground">Risky features</div>
            <div className="mt-1 text-muted-foreground">
              {enabledRiskyFeatures.length
                ? enabledRiskyFeatures.map(([name, feature]) => `${name} (${feature.env_key})`).join(", ")
                : "No risky feature toggles are currently enabled."}
            </div>
          </div>
          <div className="rounded-lg border px-3 py-2">
            <div className="font-semibold text-foreground">Provider keys</div>
            <div className="mt-1 text-muted-foreground">
              {providerEnvKeys.length
                ? providerEnvKeys.map((secret) => `${secret.provider}: ${secret.masked || "env configured"}`).join(", ")
                : "No provider keys detected in plain environment variables."}
            </div>
          </div>
          <div className="rounded-lg border px-3 py-2">
            <div className="font-semibold text-foreground">Operator-managed items</div>
            <div className="mt-1 text-muted-foreground">
              {securityStatus?.operator_guidance.map((item) => item.area).join(", ") ?? "DNS, TLS, firewall, SSH, Docker, provider rotation, and port bindings."}
            </div>
          </div>
        </div>
        <div className="rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
          Rules apply when Security is on. Vault, destructive edits, deletes, and external sends still use the existing approval and break-glass protections.
        </div>
      </CardContent>
    </Card>
  )
}

function StatusPill({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-lg border px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      <Badge variant={good ? "default" : "secondary"}>{value}</Badge>
    </div>
  )
}

function TaskGuardianCard({
  guardianStatus,
  tasks,
  runs,
  enabledTasks,
  room,
  onToggleWriteMode,
  onCreateTask,
  onRunTask,
  onSetTaskEnabled,
}: {
  guardianStatus: GuardianStatus | null
  tasks: GuardianTaskRecord[]
  runs: GuardianRunRecord[]
  enabledTasks: number
  room: RoomInfo | null
  onToggleWriteMode: () => void
  onCreateTask: (input: { name: string; toolName: string; schedule: string; args: string }) => void
  onRunTask: (taskId: string) => void
  onSetTaskEnabled: (taskId: string, enabled: boolean) => void
}) {
  const [name, setName] = useState("")
  const [toolName, setToolName] = useState(TASK_TOOL_OPTIONS[0] ?? "health_check")
  const [schedule, setSchedule] = useState("daily:13:00")
  const [args, setArgs] = useState("{}")
  const canCreate = Boolean(room && name.trim() && toolName.trim() && schedule.trim())

  function submitTask() {
    if (!canCreate) return
    onCreateTask({ name: name.trim(), toolName, schedule: schedule.trim(), args })
    setName("")
    setArgs("{}")
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <ClipboardList className="size-4" />
              Task Guardian
            </CardTitle>
            <CardDescription>Room jobs and runtime write-mode controls from the existing Guardian system.</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={guardianStatus?.task_guardian_enabled ? "default" : "secondary"}>
              {guardianStatus?.task_guardian_enabled ? "enabled" : "not configured"}
            </Badge>
            <Button size="sm" variant="outline" onClick={onToggleWriteMode} disabled={!guardianStatus}>
              <ShieldCheck className="mr-1.5 size-3.5" />
              {guardianStatus?.task_guardian_write_enabled ? "Write mode on" : "Read-only mode"}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2 text-sm sm:grid-cols-3">
          <Metric label="Room jobs" value={String(tasks.length)} />
          <Metric label="Enabled" value={String(enabledTasks)} />
          <Metric label="Recent runs" value={String(runs.length)} />
        </div>
        <div className="grid gap-3 rounded-lg border bg-muted/20 p-3 md:grid-cols-2">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Task name"
            className="rounded-md border bg-background px-3 py-2 text-sm outline-none"
            disabled={!room}
          />
          <select
            value={toolName}
            onChange={(event) => setToolName(event.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm outline-none"
            disabled={!room}
          >
            {TASK_TOOL_OPTIONS.map((tool) => (
              <option key={tool} value={tool}>{tool}</option>
            ))}
          </select>
          <input
            value={schedule}
            onChange={(event) => setSchedule(event.target.value)}
            placeholder="daily:13:00, every:3600, or at:2026-05-02T14:00:00Z"
            className="rounded-md border bg-background px-3 py-2 text-sm outline-none md:col-span-2"
            disabled={!room}
          />
          <textarea
            value={args}
            onChange={(event) => setArgs(event.target.value)}
            placeholder='{"max_emails": 5}'
            rows={3}
            className="rounded-md border bg-background px-3 py-2 font-mono text-sm outline-none md:col-span-2"
            disabled={!room}
          />
          <div className="md:col-span-2 flex justify-end">
            <Button size="sm" onClick={submitTask} disabled={!canCreate}>
              Create scheduled job
            </Button>
          </div>
        </div>
        {!room ? (
          <div className="rounded-lg border border-dashed px-3 py-3 text-sm text-muted-foreground">
            No room context is available, so room-specific Task Guardian actions are read-only.
          </div>
        ) : tasks.length === 0 ? (
          <div className="rounded-lg border border-dashed px-3 py-3 text-sm text-muted-foreground">
            No Task Guardian jobs are configured for {room.name}. Job creation remains available through the existing room scheduler APIs.
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => (
              <div key={task.id} className="rounded-lg border px-3 py-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium">{task.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {task.tool_name} - {task.schedule}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => onRunTask(task.id)}>
                      Run now
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => onSetTaskEnabled(task.id, !task.enabled)}>
                      {task.enabled ? "Pause" : "Resume"}
                    </Button>
                  </div>
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  {task.next_run_at ? `Next: ${new Date(task.next_run_at).toLocaleString()}` : "No next run scheduled"}
                  {task.last_status ? ` - Last: ${task.last_status}` : ""}
                  {task.last_message ? ` - ${task.last_message}` : ""}
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Recent runs</div>
          {runs.length === 0 ? (
            <div className="text-sm text-muted-foreground">No recent Task Guardian runs.</div>
          ) : (
            runs.slice(0, 5).map((run) => (
              <div key={run.run_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm">
                <span className="font-medium">{run.status.toUpperCase()}</span>
                <span className="text-xs text-muted-foreground">{formatRelativeTime(run.created_at)}</span>
                {run.message ? <span className="basis-full text-xs text-muted-foreground">{run.message}</span> : null}
              </div>
            ))
          )}
        </div>
        <div className="rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
          Write mode is runtime-scoped and resets to the environment default after process restart.
        </div>
      </CardContent>
    </Card>
  )
}
