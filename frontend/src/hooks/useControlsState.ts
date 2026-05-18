// Shared controls state hook — used by both SparkbotDmPage and Command Center

import { useState, useCallback, useEffect } from "react"
import { apiFetch } from "@/lib/apiBase"
import {
  CONTROLS_ONBOARDING_KEY,
  controlsOnboardingComplete,
} from "@/lib/sparkbotControls"

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ModelsControlsConfig {
  active_model: string
  token_guardian_mode: string
  stack: {
    primary: string
    backup_1: string
    backup_2: string
    heavy_hitter: string
  }
  providers: Array<{
    id: string
    label: string
    configured: boolean
    reachable?: boolean | null
    models_available?: boolean | null
    available_models?: string[]
    models: string[]
    auth_modes?: string[]
    saved_auth_mode?: string
  }>
  default_selection: {
    provider: string
    model: string
    label?: string
  }
  local_runtime: {
    default_local_model: string
    base_url: string
    ollama_base_url?: string
    local_ai_base_url?: string
    local_runtime?: string
    model_id?: string
    enabled?: boolean
    auth_mode?: "none" | "api_key"
    local_ai_status?: {
      reachable: boolean
      base_url: string
      models: string[]
      model_ids?: string[]
      models_available?: boolean
      local_runtime?: string
    }
  }
  routing_policy?: {
    default_provider_authoritative: boolean
    cross_provider_fallback: boolean
  }
  global_computer_control?: boolean
  global_computer_control_expires_at?: number | null
  global_computer_control_ttl_remaining?: number | null
  security_guardrails_enabled?: boolean
  security_profile?: {
    id: "personal" | "balanced" | "locked" | "custom"
    label: string
    status?: string
  }
  security_profiles?: Array<{
    id: "personal" | "balanced" | "locked" | "custom"
    label: string
    description: string
  }>
  custom_guardrails?: string
  agent_overrides: Record<string, { route: string; model?: string; model_seat_id?: string }>
  model_seats?: Array<{
    id: string
    label: string
    company?: string
    provider: string
    auth_mode?: "none" | "api_key" | "oauth" | "codex_sub"
    model_id?: string
    local_runtime?: string
    base_url?: string
    enabled: boolean
    show_in_round_table: boolean
    show_in_specialty_wing: boolean
    notes?: string
    configured?: boolean
    credential_configured?: boolean
    setup_status?: "ready" | "setup_needed" | "unreachable" | "disabled" | string
    setup_message?: string
  }>
  available_agents: Array<{
    name: string
    emoji: string
    description: string
    is_builtin?: boolean
  }>
  model_labels?: Record<string, string>
  ollama_status?: {
    reachable: boolean
    base_url: string
    models: string[]
    model_ids?: string[]
    models_available?: boolean
  }
  local_ai_status?: {
    reachable: boolean
    base_url: string
    models: string[]
    model_ids?: string[]
    models_available?: boolean
    local_runtime?: string
  }
  comms: {
    telegram: {
      configured: boolean
      poll_enabled: boolean
      private_only: boolean
      linked_chats: number
    }
    discord: {
      configured: boolean
      enabled: boolean
      dm_only: boolean
      linked_channels: number
    }
    whatsapp: {
      configured: boolean
      enabled: boolean
      linked_numbers: number
    }
    github: {
      configured: boolean
      enabled: boolean
      token_configured?: boolean
      ssh_configured?: boolean
      app_configured?: boolean
      bot_login: string
      default_repo: string
      allowed_repos: string[]
      allowed_repos_count: number
      linked_threads: number
      webhook_path: string
      webhook_configured?: boolean
    }
    google: {
      gmail_configured: boolean
      calendar_configured: boolean
      drive_configured?: boolean
      docs_configured?: boolean
      shared_drive_configured?: boolean
    }
    microsoft?: {
      configured: boolean
      outlook_configured: boolean
      calendar_configured: boolean
      onedrive_configured: boolean
      tenant_id: string
    }
  }
  notices: string[]
  restart_required?: boolean
}

export interface ModelStackForm {
  primary: string
  backup_1: string
  backup_2: string
  heavy_hitter: string
}

export interface ProviderTokenDrafts {
  openrouter_api_key: string
  openai_api_key: string
  openai_auth_mode: "api_key" | "codex_sub"
  anthropic_api_key: string
  anthropic_auth_mode: "api_key" | "oauth"
  google_api_key: string
  groq_api_key: string
  minimax_api_key: string
  xai_api_key: string
  local_ai_runtime: string
  local_ai_base_url: string
  local_ai_model: string
  local_ai_auth_mode: "none" | "api_key"
  local_ai_enabled: string
}

export interface DefaultModelSelectionForm {
  provider: "openrouter" | "ollama" | "local_ai" | "openai" | "openai_codex" | "claude_sub" | "anthropic" | "google" | "groq" | "minimax" | "xai"
  model: string
}

export interface RoutingPolicyForm {
  crossProviderFallback: boolean
}

export interface AgentRoutingOverride {
  route: string
  model: string
  model_seat_id?: string
}

export interface ModelSeatSaveInput {
  id: string
  label?: string
  company?: string
  provider?: string
  auth_mode?: "none" | "api_key" | "oauth" | "codex_sub"
  model_id?: string
  local_runtime?: string
  base_url?: string
  enabled?: boolean
  show_in_round_table?: boolean
  show_in_specialty_wing?: boolean
  notes?: string
  credential?: string
}

export interface OpenRouterModelRecord {
  id: string
  raw_id: string
  label: string
  context_length?: number
  pricing?: Record<string, string>
  is_free?: boolean
}

export interface CommsForm {
  telegram: {
    bot_token: string
    chat_id: string
    enabled: boolean
    private_only: boolean
  }
  discord: {
    bot_token: string
    enabled: boolean
    dm_only: boolean
  }
  whatsapp: {
    token: string
    phone_id: string
    verify_token: string
    enabled: boolean
  }
  github: {
    token: string
    webhook_secret: string
    ssh_private_key: string
    ssh_key_path: string
    app_id: string
    app_installation_id: string
    app_private_key: string
    bot_login: string
    default_repo: string
    allowed_repos: string
    enabled: boolean
  }
  google: {
    client_id: string
    client_secret: string
    refresh_token: string
    calendar_id: string
    shared_drive_id: string
  }
  microsoft: {
    client_id: string
    client_secret: string
    tenant_id: string
    refresh_token: string
  }
}

export interface OllamaStatus {
  reachable: boolean
  base_url: string
  models: string[]
  model_ids?: string[]
  models_available?: boolean
}

export interface GuardianStatus {
  breakglass: { active: boolean; ttl_remaining: number | null }
  operator: { username: string; usernames_configured: boolean; open_mode: boolean }
  pin_configured: boolean
  vault_configured: boolean
  security_guardrails_enabled?: boolean
  custom_guardrails?: string
  memory_guardian_enabled: boolean
  task_guardian_enabled: boolean
  task_guardian_write_enabled: boolean
}

export interface ControlsDashboardSummary {
  summary: {
    pending_approvals: number
    guardian_jobs: number
    guardian_jobs_enabled: number
    token_guardian_mode: string
  }
  today: {
    token_guardian: {
      mode: string
      live_ready: boolean
      configured_models: string[]
      allowed_live_models: string[]
      total_tokens: number
      total_cost: number
      requests: number
      live_routes_24h: number
      suggested_switches_24h: number
      estimated_savings_24h: number
      top_models: Array<{ model: string; tokens: number }>
      last_route: {
        created_at: string
        classification: string | null
        current_model: string | null
        selected_model: string | null
        applied_model: string | null
        fallback_reason: string | null
      } | null
    }
  }
}

export interface SkillInfo {
  name: string
  description: string
  scope: string
  action_type: string
  high_risk: boolean
  requires_execution_gate: boolean
  default_action: string
}

export interface PolicyEntry {
  id: string
  created_at: string
  tool_result: {
    action?: string
    reason?: string
    resource?: string
  } | string
}

export interface GuardianTaskRecord {
  id: string
  name: string
  tool_name: string
  schedule: string
  enabled: boolean
  next_run_at?: string | null
  last_status?: string | null
  last_message?: string | null
}

export interface GuardianRunRecord {
  run_id: string
  task_id: string
  status: string
  message: string
  created_at: string
}

export interface Agent {
  name: string
  emoji: string
  description: string
  is_builtin?: boolean
}

export interface AgentUpdateDraft {
  emoji?: string
  description?: string
  system_prompt?: string
}

export interface RoomInfo {
  id: string
  name: string
  execution_allowed: boolean
  persona?: string
}

// ─── Constants ────────────────────────────────────────────────────────────────

const BUILTIN_AGENTS: Agent[] = [
  { name: "researcher", emoji: "🔍", description: "Research specialist — finds accurate info, searches the web" },
  { name: "coder",      emoji: "💻", description: "Software engineer — clean, working code with explanations" },
  { name: "writer",     emoji: "✍️", description: "Professional writer — drafts, edits, structures content" },
  { name: "analyst",    emoji: "📊", description: "Data analyst — structured reasoning and actionable insights" },
  { name: "meetings_manager", emoji: "🗓️", description: "Plans, runs, summarizes, and follows up on meetings with clear agendas, decisions, action items, owners, deadlines, and operator-ready recaps." },
  { name: "web_designer", emoji: "🎨", description: "Designs clean, modern, responsive web pages and product experiences with strong layout, copy structure, visual hierarchy, and implementation-ready specs." },
  { name: "marketing_agent", emoji: "📣", description: "Creates practical marketing strategy, landing page copy, launch messaging, social posts, positioning, and campaign plans." },
  { name: "business_analyst", emoji: "📈", description: "Turns ideas, products, operations, and technical plans into clear business requirements, risks, priorities, metrics, workflows, and execution-ready recommendations." },
]

export const AGENT_TEMPLATES = [
  { id: "custom",          label: "Custom (blank)",         emoji: "🤖", description: "", prompt: "" },
  { id: "data_scientist",  label: "Data Scientist",          emoji: "📈", description: "Python data analysis, statistics, visualization, and ML insights", prompt: "You are the Data Scientist agent. You specialize in data analysis, statistics, and machine learning. Use Python-first approaches, produce clear visualizations when helpful, and surface actionable insights. Show your methodology and confidence bounds." },
  { id: "devops",          label: "DevOps Engineer",         emoji: "🔧", description: "Infrastructure, CI/CD, Docker, Kubernetes, cloud, and automation", prompt: "You are the DevOps Engineer agent. You specialize in infrastructure, containerization, CI/CD pipelines, Kubernetes, and cloud platforms (AWS/GCP/Azure). Produce working shell scripts, Dockerfiles, and pipeline configs. Always consider security, cost, and reliability." },
  { id: "legal",           label: "Legal Advisor",           emoji: "⚖️", description: "Legal concepts, contract review, compliance guidance (informational only)", prompt: "You are the Legal Advisor agent. You help with understanding legal concepts, reviewing contract language, and identifying compliance considerations. Always clarify that your responses are informational only and not formal legal advice. Flag anything that requires a licensed attorney." },
  { id: "hr",              label: "HR Manager",              emoji: "👥", description: "Hiring, onboarding, performance reviews, HR policy, team dynamics", prompt: "You are the HR Manager agent. You help with hiring processes, job descriptions, onboarding plans, performance review frameworks, and HR policy questions. Be empathetic, legally aware (flag jurisdiction-specific considerations), and practical." },
  { id: "marketing",       label: "Marketing Specialist",    emoji: "📣", description: "Content strategy, campaign planning, brand voice, copywriting", prompt: "You are the Marketing Specialist agent. You excel at content strategy, campaign planning, SEO-aware copywriting, and social media. Tailor content to the target audience and channel. Offer multiple tone options when style matters." },
  { id: "finance",         label: "Financial Analyst",       emoji: "💰", description: "Budgeting, financial modeling, investment concepts, cost analysis", prompt: "You are the Financial Analyst agent. You help with budgeting, financial modeling, cost-benefit analysis, and interpreting financial data. Use structured tables and formulas. Distinguish between estimates and certainties, and flag when professional financial advice is warranted." },
  { id: "support",         label: "Customer Support",        emoji: "🎧", description: "Friendly, empathetic issue resolution and escalation guidance", prompt: "You are the Customer Support agent. You respond with warmth, patience, and clarity. Help resolve issues step-by-step, de-escalate frustrated customers, and know when to escalate to a human. Keep tone friendly and professional." },
  { id: "pm",              label: "Project Manager",         emoji: "📋", description: "Project planning, sprint coordination, risk tracking, stakeholder comms", prompt: "You are the Project Manager agent. You help plan projects, define milestones, track risks, write status updates, and structure team communication. Use agile or waterfall frameworks as appropriate. Be precise about timelines, owners, and dependencies." },
  { id: "security",        label: "Security Analyst",        emoji: "🔐", description: "Threat modeling, code security review, compliance, best practices", prompt: "You are the Security Analyst agent. You review code and architecture for security vulnerabilities, apply threat modeling (STRIDE, OWASP), and advise on compliance (SOC2, GDPR, ISO 27001). Be specific about severity and remediation steps." },
  { id: "tech_writer",     label: "Technical Writer",        emoji: "📝", description: "API docs, user guides, READMEs, and clear technical documentation", prompt: "You are the Technical Writer agent. You produce clear, well-structured documentation: API references, user guides, READMEs, and changelogs. Adapt tone to the audience (developer vs end-user). Always prioritize accuracy and scannability." },
]

export const TASK_TOOL_OPTIONS = [
  "sparkbot_health_check",
  "morning_briefing",
  "memory_retrieval_stats",
  "memory_reindex",
  "github_list_prs",
  "github_get_ci_status",
  "gmail_fetch_inbox",
  "gmail_search",
  "calendar_list_events",
  "slack_get_channel_history",
  "server_read_command",
  "list_tasks",
  "list_reminders",
]

const LEGACY_COMMS_VISIBLE = true

const EMPTY_COMMS: CommsForm = {
  telegram: { bot_token: "", chat_id: "", enabled: true, private_only: true },
  discord: { bot_token: "", enabled: false, dm_only: false },
  whatsapp: { token: "", phone_id: "", verify_token: "sparkbot-wa-verify", enabled: false },
  github: {
    token: "", webhook_secret: "", ssh_private_key: "", ssh_key_path: "",
    app_id: "", app_installation_id: "", app_private_key: "",
    bot_login: "sparkbot", default_repo: "", allowed_repos: "", enabled: false,
  },
  google: { client_id: "", client_secret: "", refresh_token: "", calendar_id: "", shared_drive_id: "" },
  microsoft: { client_id: "", client_secret: "", tenant_id: "common", refresh_token: "" },
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export interface UseControlsStateOptions {
  roomId: string | null
  /** Called after successful save actions (e.g. "Provider credentials saved.") */
  onStatusMessage?: (msg: string) => void
}

export function useControlsState({ roomId, onStatusMessage }: UseControlsStateOptions) {
  const notify = onStatusMessage ?? (() => {})

  // ── Core state ──────────────────────────────────────────────────────────────
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [settingsError, setSettingsError] = useState("")
  const [modelsConfig, setModelsConfig] = useState<ModelsControlsConfig | null>(null)
  const [tokenGuardianMode, setTokenGuardianMode] = useState("shadow")
  const [savingTokenGuardianMode, setSavingTokenGuardianMode] = useState(false)
  const [defaultSelection, setDefaultSelection] = useState<DefaultModelSelectionForm>({
    provider: "openrouter", model: "",
  })
  const [routingPolicy, setRoutingPolicy] = useState<RoutingPolicyForm>({
    crossProviderFallback: false,
  })
  const [localDefaultModel, setLocalDefaultModel] = useState("")
  const [agentOverrides, setAgentOverrides] = useState<Record<string, AgentRoutingOverride>>({})
  const [openRouterModels, setOpenRouterModels] = useState<OpenRouterModelRecord[]>([])
  const [loadingOpenRouterModels, setLoadingOpenRouterModels] = useState(false)
  const [openRouterLoadError, setOpenRouterLoadError] = useState("")
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus | null>(null)
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState("http://localhost:11434")
  const [ollamaLoading, setOllamaLoading] = useState(false)
  const [modelStack, setModelStack] = useState<ModelStackForm>({
    primary: "", backup_1: "", backup_2: "", heavy_hitter: "",
  })
  const [providerDrafts, setProviderDrafts] = useState<ProviderTokenDrafts>({
    openrouter_api_key: "", openai_api_key: "", openai_auth_mode: "api_key",
    anthropic_api_key: "", anthropic_auth_mode: "api_key",
    google_api_key: "", groq_api_key: "", minimax_api_key: "", xai_api_key: "",
    local_ai_runtime: "openai_compatible", local_ai_base_url: "http://localhost:1234/v1",
    local_ai_model: "", local_ai_auth_mode: "none", local_ai_enabled: "",
  })
  const [commsForm, setCommsForm] = useState<CommsForm>({ ...EMPTY_COMMS })
  const [commsOpenSection, setCommsOpenSection] = useState<string | null>(null)
  const [savingModelStack, setSavingModelStack] = useState(false)
  const [savingProviderTokens, setSavingProviderTokens] = useState(false)
  const [savingDefaultSelection, setSavingDefaultSelection] = useState(false)
  const [savingAgentOverrides, setSavingAgentOverrides] = useState(false)
  const [savingModelSeats, setSavingModelSeats] = useState(false)
  const [savingComms, setSavingComms] = useState(false)
  const [policyEntries, setPolicyEntries] = useState<PolicyEntry[]>([])
  const [guardianTasks, setGuardianTasks] = useState<GuardianTaskRecord[]>([])
  const [guardianRuns, setGuardianRuns] = useState<GuardianRunRecord[]>([])
  const [taskName, setTaskName] = useState("")
  const [taskToolName, setTaskToolName] = useState("sparkbot_health_check")
  const [taskSchedule, setTaskSchedule] = useState("daily-local:06:00")
  const [taskArgs, setTaskArgs] = useState('{"mode": "pc", "delivery_channels": ["app"]}')
  const [taskSaving, setTaskSaving] = useState(false)
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [roomPersona, setRoomPersona] = useState("")
  const [savingPersona, setSavingPersona] = useState(false)
  const [personaSaved, setPersonaSaved] = useState(false)
  const [roomInfo, setRoomInfo] = useState<RoomInfo | null>(null)
  const [guardianStatus, setGuardianStatus] = useState<GuardianStatus | null>(null)
  const [controlsDashboard, setControlsDashboard] = useState<ControlsDashboardSummary | null>(null)
  const [savingExecution, setSavingExecution] = useState(false)
  const [executionSaved, setExecutionSaved] = useState(false)
  const [executionError, setExecutionError] = useState("")
  const [customGuardrails, setCustomGuardrails] = useState("")
  const [securityProfile, setSecurityProfile] = useState<"personal" | "balanced" | "locked" | "custom">("personal")
  const [savingPin, setSavingPin] = useState(false)
  const [pinSaved, setPinSaved] = useState(false)
  const [pinError, setPinError] = useState("")
  const [agents, setAgents] = useState<Agent[]>(BUILTIN_AGENTS)

  // Spawn agent state
  const [spawnTemplate, setSpawnTemplate] = useState("custom")
  const [spawnName, setSpawnName] = useState("")
  const [spawnEmoji, setSpawnEmoji] = useState("🤖")
  const [spawnDescription, setSpawnDescription] = useState("")
  const [spawnPrompt, setSpawnPrompt] = useState("")
  const [spawning, setSpawning] = useState(false)

  // ── Apply config from server ────────────────────────────────────────────────
  const applyControlsConfig = useCallback((config: ModelsControlsConfig) => {
    if (!config?.default_selection) return
    setModelsConfig(config)
    setTokenGuardianMode(config.token_guardian_mode || "shadow")
    setCustomGuardrails(config.custom_guardrails ?? "")
    setSecurityProfile(config.security_profile?.id ?? (config.security_guardrails_enabled ? "balanced" : "personal"))
    setModelStack(prev => config.stack ?? prev)
    const validProviders = new Set(["openrouter", "ollama", "local_ai", "openai", "openai_codex", "claude_sub", "anthropic", "google", "groq", "minimax", "xai"])
    const savedProvider = config.default_selection?.provider ?? "openrouter"
    const resolvedProvider = (validProviders.has(savedProvider) ? savedProvider : "openrouter")
    const savedModel = config.default_selection?.model || ""
    setDefaultSelection({
      provider: resolvedProvider as DefaultModelSelectionForm["provider"],
      model: savedModel,
    })
    setRoutingPolicy({
      crossProviderFallback: Boolean(config.routing_policy?.cross_provider_fallback),
    })
    setProviderDrafts((prev) => ({
      ...prev,
      openai_auth_mode:
        (config.providers?.find((p) => p.id === "openai")?.saved_auth_mode as "api_key" | "codex_sub") || "api_key",
      anthropic_auth_mode:
        (config.providers?.find((p) => p.id === "anthropic")?.saved_auth_mode as "api_key" | "oauth") || "api_key",
      local_ai_runtime: config.local_runtime?.local_runtime || "openai_compatible",
      local_ai_base_url: config.local_runtime?.local_ai_base_url || config.local_ai_status?.base_url || "http://localhost:1234/v1",
      local_ai_model: config.local_runtime?.model_id || "",
      local_ai_auth_mode: (config.local_runtime?.auth_mode as "none" | "api_key") || "none",
      local_ai_enabled: config.local_runtime?.enabled ? "true" : "",
    }))
    setLocalDefaultModel(config.local_runtime?.default_local_model || "")
    setAgentOverrides(
      Object.fromEntries(
        (config.available_agents ?? []).map((agent) => [
          agent.name,
          {
            route: config.agent_overrides?.[agent.name]?.route ?? "default",
            model: config.agent_overrides?.[agent.name]?.model ?? "",
            model_seat_id: config.agent_overrides?.[agent.name]?.model_seat_id ?? "",
          },
        ]),
      ),
    )
    setCommsForm({
      telegram: {
        bot_token: "", chat_id: "",
        enabled: Boolean(config.comms?.telegram?.poll_enabled),
        private_only: Boolean(config.comms?.telegram?.private_only ?? true),
      },
      discord: {
        bot_token: "",
        enabled: Boolean(config.comms?.discord?.enabled),
        dm_only: Boolean(config.comms?.discord?.dm_only),
      },
      whatsapp: {
        token: "", phone_id: "", verify_token: "sparkbot-wa-verify",
        enabled: Boolean(config.comms?.whatsapp?.enabled),
      },
      github: {
        token: "", webhook_secret: "", ssh_private_key: "", ssh_key_path: "",
        app_id: "", app_installation_id: "", app_private_key: "",
        bot_login: config.comms?.github?.bot_login || "sparkbot",
        default_repo: config.comms?.github?.default_repo || "",
        allowed_repos: (config.comms?.github?.allowed_repos ?? []).join(", "),
        enabled: Boolean(config.comms?.github?.enabled),
      },
      google: { client_id: "", client_secret: "", refresh_token: "", calendar_id: "", shared_drive_id: "" },
      microsoft: { client_id: "", client_secret: "", tenant_id: config.comms?.microsoft?.tenant_id || "common", refresh_token: "" },
    })
    setOllamaBaseUrl(config.local_runtime?.base_url || "http://localhost:11434")
    if (config.ollama_status) {
      setOllamaStatus({
        reachable: Boolean(config.ollama_status.reachable),
        base_url: config.ollama_status.base_url || config.local_runtime?.base_url || "http://localhost:11434",
        models: config.ollama_status.models ?? [],
        model_ids: config.ollama_status.model_ids ?? [],
        models_available: Boolean(config.ollama_status.models_available),
      })
    }
    if (controlsOnboardingComplete(config as never)) {
      localStorage.setItem(CONTROLS_ONBOARDING_KEY, "true")
    } else {
      localStorage.removeItem(CONTROLS_ONBOARDING_KEY)
    }
  }, [])

  // ── Refresh all controls data ───────────────────────────────────────────────
  const refreshControls = useCallback(async () => {
    if (!roomId) return
    setSettingsLoading(true)
    setSettingsError("")
    try {
      const safe = (p: Promise<Response>) => p.catch(() => null)
      const [roomRes, policyRes, tasksRes, runsRes, dashboardRes, modelsConfigRes, guardianStatusRes] = await Promise.all([
        safe(apiFetch(`/api/v1/chat/rooms/${roomId}`, { credentials: "include" })),
        safe(apiFetch(`/api/v1/chat/audit?limit=10&room_id=${roomId}&tool=policy_decision`, { credentials: "include" })),
        safe(apiFetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks?limit=20`, { credentials: "include" })),
        safe(apiFetch(`/api/v1/chat/rooms/${roomId}/guardian/runs?limit=10`, { credentials: "include" })),
        safe(apiFetch("/api/v1/chat/dashboard/summary", { credentials: "include" })),
        safe(apiFetch("/api/v1/chat/models/config", { credentials: "include" })),
        safe(apiFetch("/api/v1/chat/guardian/status", { credentials: "include" })),
      ])

      if (roomRes?.ok) {
        try {
          const roomData = await roomRes.json()
          setRoomInfo(roomData)
          setRoomPersona(roomData.persona ?? "")
        } catch { /* ignore */ }
      }
      if (policyRes?.ok) {
        try { const data = await policyRes.json(); setPolicyEntries(data.items ?? []) } catch { /* ignore */ }
      }
      if (tasksRes?.ok) {
        try { const data = await tasksRes.json(); setGuardianTasks(data.items ?? []) } catch { /* ignore */ }
      }
      if (runsRes?.ok) {
        try { const data = await runsRes.json(); setGuardianRuns(data.items ?? []) } catch { /* ignore */ }
      }
      if (dashboardRes?.ok) {
        try { setControlsDashboard(await dashboardRes.json()) } catch { /* ignore */ }
      }
      if (guardianStatusRes?.ok) {
        try { setGuardianStatus(await guardianStatusRes.json()) } catch { /* ignore */ }
      }
      if (modelsConfigRes?.ok) {
        try {
          const config = await modelsConfigRes.json()
          applyControlsConfig(config)
        } catch { /* ignore */ }
      } else if (modelsConfigRes && !modelsConfigRes.ok) {
        setSettingsError("Could not load Sparkbot controls. Check that the backend is running.")
      }
      // Fetch skill list (best-effort)
      try {
        const skillsRes = await apiFetch("/api/v1/chat/skills", { credentials: "include" })
        if (skillsRes.ok) { const d = await skillsRes.json(); setSkills(d.skills ?? []) }
      } catch { /* ignore */ }
      // Check Ollama status (best-effort)
      try {
        const ollamaRes = await apiFetch("/api/v1/chat/ollama/status", { credentials: "include" })
        if (ollamaRes.ok) {
          const data: OllamaStatus = await ollamaRes.json()
          setOllamaStatus(data)
          setOllamaBaseUrl(data.base_url)
        }
      } catch { /* ignore */ }
      // Load agents (best-effort)
      try {
        const agentsRes = await apiFetch("/api/v1/chat/agents", { credentials: "include" })
        if (agentsRes.ok) { const ag = await agentsRes.json(); setAgents(ag.agents ?? BUILTIN_AGENTS) }
      } catch { /* ignore */ }
    } catch {
      setSettingsError("Could not load Sparkbot controls. Try restarting Sparkbot.")
    } finally {
      setSettingsLoading(false)
    }
  }, [roomId, applyControlsConfig])

  // ── Load OpenRouter models ──────────────────────────────────────────────────
  const loadOpenRouterModels = useCallback(async () => {
    setLoadingOpenRouterModels(true)
    setOpenRouterLoadError("")
    try {
      const response = await apiFetch("/api/v1/chat/openrouter/models", { credentials: "include" })
      const contentType = response.headers.get("content-type") || ""
      if (!response.ok) {
        let detail = `HTTP ${response.status}`
        if (contentType.includes("application/json")) {
          const errData = await response.json().catch(() => ({ detail }))
          detail = errData.detail ?? detail
        } else {
          const text = await response.text().catch(() => "")
          if (text.includes("<!DOCTYPE") || text.includes("<html")) {
            detail = "Sparkbot got the desktop page instead of the backend API. Restart the app and try again."
          }
        }
        throw new Error(detail)
      }
      if (!contentType.includes("application/json")) {
        const text = await response.text().catch(() => "")
        if (text.includes("<!DOCTYPE") || text.includes("<html")) {
          throw new Error("Sparkbot got the desktop page instead of the backend API. Restart the app and try again.")
        }
        throw new Error("OpenRouter model refresh returned a non-JSON response.")
      }
      const data = await response.json()
      setOpenRouterModels(data.models ?? [])
    } catch (err) {
      setOpenRouterModels([])
      setOpenRouterLoadError(err instanceof Error ? err.message : "Failed to load OpenRouter models")
    } finally {
      setLoadingOpenRouterModels(false)
    }
  }, [])

  // Auto-select first free OpenRouter model once loaded
  useEffect(() => {
    if (openRouterModels.length === 0) return
    setDefaultSelection(prev => {
      if (prev.provider === "openrouter" && !prev.model) {
        const firstFree = openRouterModels.find(m => m.is_free) ?? openRouterModels[0]
        return { ...prev, model: firstFree.id }
      }
      return prev
    })
  }, [openRouterModels])

  // ── Save callbacks ──────────────────────────────────────────────────────────

  const toggleExecutionGate = useCallback(async (enabled: boolean) => {
    setSavingExecution(true)
    setExecutionError("")
    setExecutionSaved(false)
    try {
      const securityRes = await apiFetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ security_guardrails_enabled: enabled }),
      })
      if (!securityRes.ok) {
        const data = await securityRes.json().catch(() => ({ detail: "Could not update Security guardrails." }))
        setExecutionError(data.detail ?? "Could not update Security guardrails.")
        return
      }
      const securityData = await securityRes.json().catch(() => null)
      if (securityData) applyControlsConfig(securityData)
      setExecutionSaved(true)
      notify(enabled ? "Security guardrails enabled." : "Security guardrails disabled.")
      setTimeout(() => setExecutionSaved(false), 3000)
    } catch {
      setExecutionError("Could not update Security guardrails.")
    } finally {
      setSavingExecution(false)
    }
  }, [applyControlsConfig, notify])

  const saveSecurityProfile = useCallback(async (profile: "personal" | "balanced" | "locked" | "custom") => {
    setSavingExecution(true)
    setExecutionError("")
    setExecutionSaved(false)
    try {
      const res = await apiFetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ security_profile: profile }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save Security profile." }))
      if (!res.ok) {
        setExecutionError(data.detail ?? "Could not save Security profile.")
        return
      }
      applyControlsConfig(data)
      setExecutionSaved(true)
      notify(`Security profile set to ${data.security_profile?.label ?? profile}.`)
      setTimeout(() => setExecutionSaved(false), 3000)
    } catch {
      setExecutionError("Could not save Security profile.")
    } finally {
      setSavingExecution(false)
    }
  }, [applyControlsConfig, notify])

  const saveCustomGuardrails = useCallback(async () => {
    setSavingExecution(true)
    setExecutionError("")
    setExecutionSaved(false)
    try {
      const res = await apiFetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ custom_guardrails: customGuardrails }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save custom guardrails." }))
      if (!res.ok) {
        setExecutionError(data.detail ?? "Could not save custom guardrails.")
        return
      }
      applyControlsConfig(data)
      setExecutionSaved(true)
      notify("Custom Security guardrails saved.")
      setTimeout(() => setExecutionSaved(false), 3000)
    } catch {
      setExecutionError("Could not save custom guardrails.")
    } finally {
      setSavingExecution(false)
    }
  }, [applyControlsConfig, customGuardrails, notify])

  const saveOperatorPin = useCallback(async (currentPin: string, pin: string, pinConfirm: string) => {
    setSavingPin(true)
    setPinError("")
    setPinSaved(false)
    try {
      const res = await apiFetch("/api/v1/chat/guardian/pin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ current_pin: currentPin || null, pin, pin_confirm: pinConfirm }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save PIN." }))
      if (!res.ok) {
        setPinError(data.detail ?? "Could not save PIN.")
      } else {
        setPinSaved(true)
        setGuardianStatus(prev => prev ? { ...prev, pin_configured: true } : prev)
        await refreshControls()
        setTimeout(() => setPinSaved(false), 3000)
      }
    } catch {
      setPinError("Could not save PIN.")
    } finally {
      setSavingPin(false)
    }
  }, [refreshControls])

  const savePersona = useCallback(async () => {
    if (!roomId) return
    setSavingPersona(true)
    setSettingsError("")
    try {
      const res = await apiFetch(`/api/v1/chat/rooms/${roomId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ persona: roomPersona }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Could not save persona." }))
        setSettingsError(data.detail ?? "Could not save persona.")
      } else {
        const data = await res.json()
        setRoomInfo(data)
        setRoomPersona(data.persona ?? "")
        setPersonaSaved(true)
        setTimeout(() => setPersonaSaved(false), 3000)
      }
    } catch {
      setSettingsError("Could not save persona.")
    } finally {
      setSavingPersona(false)
    }
  }, [roomId, roomPersona])

  const spawnAgent = useCallback(async () => {
    const name = spawnName.trim().toLowerCase().replace(/\s+/g, "_")
    if (!name || !spawnPrompt.trim()) return
    setSpawning(true)
    setSettingsError("")
    try {
      const res = await apiFetch("/api/v1/chat/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name, emoji: spawnEmoji, description: spawnDescription, system_prompt: spawnPrompt }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Could not spawn agent." }))
        setSettingsError(data.detail ?? "Could not spawn agent.")
      } else {
        const data = await res.json()
        const nextAgent = { name: data.name, emoji: data.emoji, description: data.description, is_builtin: false }
        setAgents(prev => [...prev.filter(a => a.name !== name), nextAgent])
        setModelsConfig(prev => prev ? {
          ...prev,
          available_agents: [...(prev.available_agents ?? []).filter(a => a.name !== name), nextAgent],
          agent_overrides: {
            ...(prev.agent_overrides ?? {}),
            [name]: prev.agent_overrides?.[name] ?? { route: "default" },
          },
        } : prev)
        setSpawnName(""); setSpawnEmoji("🤖"); setSpawnDescription(""); setSpawnPrompt(""); setSpawnTemplate("custom")
      }
    } catch { setSettingsError("Could not spawn agent.") } finally { setSpawning(false) }
  }, [spawnName, spawnEmoji, spawnDescription, spawnPrompt])

  const updateAgent = useCallback(async (name: string, draft: AgentUpdateDraft) => {
    const payload: AgentUpdateDraft = {}
    if (draft.emoji !== undefined) payload.emoji = draft.emoji
    if (draft.description !== undefined) payload.description = draft.description
    if (draft.system_prompt?.trim()) payload.system_prompt = draft.system_prompt.trim()
    setSettingsError("")
    const res = await apiFetch(`/api/v1/chat/agents/${encodeURIComponent(name)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    })
    const data = await res.json().catch(() => ({ detail: "Could not update agent." }))
    if (!res.ok) {
      setSettingsError(data.detail ?? "Could not update agent.")
      throw new Error(data.detail ?? "Could not update agent.")
    }
    const nextAgent = { name: data.name, emoji: data.emoji, description: data.description, is_builtin: false }
    setAgents(prev => [...prev.filter(a => a.name !== name), nextAgent])
    setModelsConfig(prev => prev ? {
      ...prev,
      available_agents: [...(prev.available_agents ?? []).filter(a => a.name !== name), nextAgent],
    } : prev)
    notify(`Agent **@${data.name}** updated.`)
  }, [notify])

  const handleDefaultSelectionChange = useCallback((field: keyof DefaultModelSelectionForm, value: string) => {
    if (field === "provider") {
      const validProviders = new Set(["openrouter", "ollama", "local_ai", "openai", "openai_codex", "claude_sub", "anthropic", "google", "groq", "minimax", "xai"])
      const nextProvider = (validProviders.has(value) ? value : "openrouter") as DefaultModelSelectionForm["provider"]
      setDefaultSelection((prev) => {
        let nextModel = ""
        if (nextProvider === "ollama") {
          nextModel = localDefaultModel
        } else if (nextProvider === "local_ai") {
          nextModel = providerDrafts.local_ai_model || modelsConfig?.local_ai_status?.model_ids?.[0] || "local/local-model"
        } else if (nextProvider === "openrouter") {
          if (prev.model.startsWith("openrouter/")) {
            nextModel = prev.model
          } else {
            const firstFree = openRouterModels.find(m => m.is_free) ?? openRouterModels[0]
            nextModel = firstFree?.id ?? ""
          }
        } else if (nextProvider === "openai_codex") {
          nextModel = modelsConfig?.providers?.find((p) => p.id === "openai_codex")?.models?.[0]
            ?? "openai-codex/gpt-5.3-codex"
        } else if (nextProvider === "claude_sub") {
          nextModel = modelsConfig?.providers?.find((p) => p.id === "claude_sub")?.models?.[0]
            ?? "claude-sub/sonnet"
        }
        return { provider: nextProvider, model: nextModel }
      })
      return
    }
    setDefaultSelection((prev) => ({ ...prev, [field]: value }))
  }, [localDefaultModel, modelsConfig?.providers, modelsConfig?.local_ai_status?.model_ids, openRouterModels, providerDrafts.local_ai_model])

  const handleLocalDefaultModelChange = useCallback((value: string) => {
    setLocalDefaultModel(value)
    setDefaultSelection((prev) => (
      prev.provider === "ollama" || prev.provider === "local_ai" ? { ...prev, model: value } : prev
    ))
  }, [])

  const handleRoutingPolicyChange = useCallback((value: boolean) => {
    setRoutingPolicy({ crossProviderFallback: value })
  }, [])

  const handleModelStackChange = useCallback((field: keyof ModelStackForm, value: string) => {
    setModelStack((prev) => ({ ...prev, [field]: value }))
  }, [])

  const handleAgentOverrideChange = useCallback((
    agentName: string,
    field: keyof AgentRoutingOverride,
    value: string,
  ) => {
    const routeToProviderPrefix: Record<string, string> = {
      openrouter: "openrouter/", local: "ollama/", openai: "gpt-", openai_codex: "openai-codex/", anthropic: "claude",
      local_ai: "local/", claude_sub: "claude-sub/", google: "gemini/", groq: "groq/", minimax: "minimax/", xai: "xai/",
    }
    setAgentOverrides((prev) => {
      const current = prev[agentName] ?? { route: "default", model: "" }
      if (field === "route") {
        const nextRoute = value
        if (nextRoute === "default") {
          return { ...prev, [agentName]: { route: "default", model: "", model_seat_id: "" } }
        }
        const prefix = routeToProviderPrefix[nextRoute] ?? ""
        const modelFits = prefix && current.model.startsWith(prefix)
        const modelSeatFits = modelFits
          && modelsConfig?.model_seats?.some((seat) => seat.id === current.model_seat_id && seat.model_id === current.model)
        return {
          ...prev,
          [agentName]: {
            route: nextRoute,
            model: modelFits ? current.model : "",
            model_seat_id: modelSeatFits ? current.model_seat_id : "",
          },
        }
      }
      if (field === "model") {
        const seat = modelsConfig?.model_seats?.find((item) =>
          item.show_in_specialty_wing
          && item.enabled
          && item.model_id === value
        )
        return { ...prev, [agentName]: { ...current, model: value, model_seat_id: seat?.id ?? "" } }
      }
      return { ...prev, [agentName]: { ...current, [field]: value } }
    })
  }, [modelsConfig?.model_seats])

  const saveProviderTokens = useCallback(async () => {
    const payload = Object.fromEntries(
      Object.entries(providerDrafts).filter(([key, value]) => {
        if (!value.trim()) return false
        if (key.startsWith("local_ai_")) return defaultSelection.provider === "local_ai"
        return true
      })
    )
    if (!Object.keys(payload).length) {
      setSettingsError("Paste at least one provider credential before saving.")
      return
    }
    setSavingProviderTokens(true)
    setSettingsError("")
    try {
      const res = await apiFetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ providers: payload }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save provider tokens." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save provider tokens.")
      } else {
        applyControlsConfig(data)
        await refreshControls()
        setProviderDrafts({
          openrouter_api_key: "", openai_api_key: "", openai_auth_mode: providerDrafts.openai_auth_mode,
          anthropic_api_key: "", anthropic_auth_mode: providerDrafts.anthropic_auth_mode,
          google_api_key: "", groq_api_key: "", minimax_api_key: "", xai_api_key: "",
          local_ai_runtime: providerDrafts.local_ai_runtime,
          local_ai_base_url: providerDrafts.local_ai_base_url,
          local_ai_model: providerDrafts.local_ai_model,
          local_ai_auth_mode: providerDrafts.local_ai_auth_mode,
          local_ai_enabled: providerDrafts.local_ai_enabled,
        })
        if (payload.openrouter_api_key) {
          await loadOpenRouterModels()
        }
        notify("Provider credentials saved.")
      }
    } catch {
      setSettingsError("Could not save provider credentials.")
    } finally {
      setSavingProviderTokens(false)
    }
  }, [applyControlsConfig, defaultSelection.provider, loadOpenRouterModels, providerDrafts, refreshControls, notify])

  const saveModelStack = useCallback(async () => {
    if (!modelStack?.primary?.trim() || !modelStack?.heavy_hitter?.trim()) {
      setSettingsError("Choose at least the primary and heavy-hitter models before saving the stack.")
      return
    }
    setSavingModelStack(true)
    setSettingsError("")
    try {
      const res = await apiFetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ stack: modelStack }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save model stack." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save model stack.")
      } else {
        applyControlsConfig(data)
        await refreshControls()
        notify("Four-model stack saved.")
      }
    } catch {
      setSettingsError("Could not save model stack.")
    } finally {
      setSavingModelStack(false)
    }
  }, [applyControlsConfig, modelStack, refreshControls, notify])

  const pageHasOpenRouterConfigured = Boolean(
    modelsConfig?.providers?.find((p) => p.id === "openrouter")?.configured,
  )

  const saveDefaultSelection = useCallback(async () => {
    const chosenDefaultModel = defaultSelection.provider === "ollama"
      ? localDefaultModel
      : defaultSelection.provider === "local_ai"
      ? (defaultSelection.model.trim() || providerDrafts.local_ai_model.trim() || "local/local-model")
      : defaultSelection.model.trim()
    const chosenLocalModel = (defaultSelection.provider === "local_ai" ? chosenDefaultModel : localDefaultModel).trim()

    if (!chosenDefaultModel) {
      const providerNames: Record<string, string> = {
        openrouter: "OpenRouter", ollama: "Ollama", local_ai: "Local AI endpoint", openai: "OpenAI", openai_codex: "OpenAI Codex Subscription",
        anthropic: "Anthropic", google: "Google", groq: "Groq", minimax: "MiniMax", xai: "xAI",
      }
      const pName = providerNames[defaultSelection.provider] ?? defaultSelection.provider
      setSettingsError(
        defaultSelection.provider === "openrouter"
          ? "Choose an OpenRouter model before saving the default."
          : defaultSelection.provider === "ollama"
          ? "Choose a local Ollama model before saving the default."
          : defaultSelection.provider === "local_ai"
          ? "Enter a local model id before saving the default."
          : `Choose a ${pName} model before saving the default.`,
      )
      return
    }
    const selectedIsFreeOpenRouterModel = openRouterModels.find(m => m.id === chosenDefaultModel)?.is_free ?? false
    if (defaultSelection.provider === "openrouter" && !pageHasOpenRouterConfigured && !providerDrafts.openrouter_api_key.trim() && !selectedIsFreeOpenRouterModel) {
      setSettingsError("This is a paid OpenRouter model. Save an OpenRouter API key before setting it as default.")
      return
    }
    if (
      defaultSelection.provider === "openai_codex"
      && !modelsConfig?.providers?.find((p) => p.id === "openai_codex")?.configured
    ) {
      setSettingsError("Sign in with ChatGPT through Codex CLI before using Codex subscription as the default.")
      return
    }
    const directKeyFields: Record<string, keyof ProviderTokenDrafts> = {
      openai: "openai_api_key", anthropic: "anthropic_api_key",
      google: "google_api_key", groq: "groq_api_key", minimax: "minimax_api_key", xai: "xai_api_key",
    }
    const directNames: Record<string, string> = {
      openai: "OpenAI", anthropic: "Anthropic", google: "Google", groq: "Groq", minimax: "MiniMax", xai: "xAI",
    }
    const directKeyField = directKeyFields[defaultSelection.provider]
    if (directKeyField) {
      const isConfigured = Boolean(modelsConfig?.providers?.find(p => p.id === defaultSelection.provider)?.configured)
      if (!isConfigured && !providerDrafts[directKeyField].trim()) {
        const name = directNames[defaultSelection.provider] ?? defaultSelection.provider
        setSettingsError(`Save a ${name} API key before using ${name} as the default.`)
        return
      }
    }

    setSavingDefaultSelection(true)
    setSettingsError("")
    try {
      const hasOrKeyDraft = defaultSelection.provider === "openrouter" && providerDrafts.openrouter_api_key.trim().length > 0
      const requestBody: Record<string, unknown> = {
        default_selection: { provider: defaultSelection.provider, model: chosenDefaultModel },
        routing_policy: { cross_provider_fallback: routingPolicy.crossProviderFallback },
      }
      if (chosenLocalModel) {
        requestBody.local_runtime = defaultSelection.provider === "local_ai"
          ? {
              default_local_model: chosenLocalModel.startsWith("local/") ? chosenLocalModel : `local/${chosenLocalModel}`,
              model_id: chosenLocalModel.startsWith("local/") ? chosenLocalModel : `local/${chosenLocalModel}`,
              local_runtime: providerDrafts.local_ai_runtime || "openai_compatible",
              base_url: providerDrafts.local_ai_base_url || "http://localhost:1234/v1",
              auth_mode: providerDrafts.local_ai_auth_mode || "none",
              enabled: true,
            }
          : {
              default_local_model: chosenLocalModel,
              local_runtime: "ollama",
              base_url: ollamaBaseUrl,
            }
      }
      if (hasOrKeyDraft) {
        requestBody.providers = { openrouter_api_key: providerDrafts.openrouter_api_key.trim() }
      }
      const res = await apiFetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(requestBody),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save default model." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save default model.")
      } else {
        applyControlsConfig(data)
        await refreshControls()
        if (hasOrKeyDraft) {
          setProviderDrafts(prev => ({ ...prev, openrouter_api_key: "" }))
          await loadOpenRouterModels()
        }
        notify(
          defaultSelection.provider === "ollama"
            ? `Default local model set to **${chosenDefaultModel}**.`
            : defaultSelection.provider === "local_ai"
            ? `Default local AI endpoint model set to **${chosenDefaultModel}**.`
            : `Default model set to **${chosenDefaultModel}**.`,
        )
      }
    } catch {
      setSettingsError("Could not save default model.")
    } finally {
      setSavingDefaultSelection(false)
    }
  }, [
    applyControlsConfig, defaultSelection, loadOpenRouterModels, routingPolicy.crossProviderFallback,
    localDefaultModel, modelsConfig, ollamaBaseUrl, pageHasOpenRouterConfigured, providerDrafts, refreshControls, openRouterModels, notify,
  ])

  const saveAgentOverrides = useCallback(async () => {
    const routingAgentList = modelsConfig?.available_agents ?? []
    if (!routingAgentList.length) {
      setSettingsError("No agents are available for override routing yet.")
      return
    }
    const payload = Object.fromEntries(
      routingAgentList.map((agent) => {
        const override = agentOverrides[agent.name] ?? { route: "default", model: "" }
        if (override.route === "default") return [agent.name, { route: "default", model: "", model_seat_id: "" }]
        const model = override.model.trim()
        const matchedSeat = modelsConfig?.model_seats?.find((seat) =>
          seat.show_in_specialty_wing
          && seat.enabled
          && seat.model_id === model
        )
        return [
          agent.name,
          {
            route: override.route,
            model,
            model_seat_id: override.model_seat_id || matchedSeat?.id || "",
          },
        ]
      }),
    )
    setSavingAgentOverrides(true)
    setSettingsError("")
    try {
      const res = await apiFetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ agent_overrides: payload }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save agent overrides." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save agent overrides.")
      } else {
        applyControlsConfig(data)
        await refreshControls()
        notify("Agent routing overrides updated.")
      }
    } catch {
      setSettingsError("Could not save agent overrides.")
    } finally {
      setSavingAgentOverrides(false)
    }
  }, [agentOverrides, applyControlsConfig, modelsConfig?.available_agents, modelsConfig?.model_seats, refreshControls, notify])

  const saveModelSeats = useCallback(async (modelSeats: ModelSeatSaveInput[]) => {
    setSavingModelSeats(true)
    setSettingsError("")
    try {
      const res = await apiFetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ model_seats: modelSeats }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save model seats." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save model seats.")
        throw new Error(String(data.detail ?? "Could not save model seats."))
      }
      applyControlsConfig(data)
      await refreshControls()
      notify("Model seats updated.")
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not save model seats."
      setSettingsError(message)
      throw error
    } finally {
      setSavingModelSeats(false)
    }
  }, [applyControlsConfig, refreshControls, notify])

  const saveComms = useCallback(async () => {
    setSavingComms(true)
    setSettingsError("")
    try {
      const res = await apiFetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ comms: commsForm }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save comms settings." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save comms settings.")
      } else {
        applyControlsConfig(data)
        await refreshControls()
        notify("Communications settings saved.")
      }
    } catch {
      setSettingsError("Could not save comms settings.")
    } finally {
      setSavingComms(false)
    }
  }, [applyControlsConfig, commsForm, refreshControls, notify])

  const saveTokenGuardianMode = useCallback(async () => {
    setSavingTokenGuardianMode(true)
    setSettingsError("")
    try {
      const res = await apiFetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ token_guardian_mode: tokenGuardianMode }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save Token Guardian mode." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save Token Guardian mode.")
      } else {
        applyControlsConfig(data)
        await refreshControls()
        notify(`Token Guardian set to **${tokenGuardianMode}**.`)
      }
    } catch {
      setSettingsError("Could not save Token Guardian mode.")
    } finally {
      setSavingTokenGuardianMode(false)
    }
  }, [applyControlsConfig, tokenGuardianMode, refreshControls, notify])

  const checkOllamaStatus = useCallback(async () => {
    setOllamaLoading(true)
    try {
      const res = await apiFetch("/api/v1/chat/ollama/status", { credentials: "include" })
      if (res.ok) {
        const data: OllamaStatus = await res.json()
        setOllamaStatus(data)
        setOllamaBaseUrl(data.base_url)
      } else {
        setOllamaStatus({ reachable: false, base_url: ollamaBaseUrl, models: [] })
      }
    } catch {
      setOllamaStatus({ reachable: false, base_url: ollamaBaseUrl, models: [] })
    } finally {
      setOllamaLoading(false)
    }
  }, [ollamaBaseUrl])

  const handleProviderDraftChange = useCallback((field: keyof ProviderTokenDrafts, value: string) => {
    setProviderDrafts(prev => ({ ...prev, [field]: value }))
  }, [])

  const handleCommsTextChange = useCallback((section: keyof CommsForm, field: string, value: string) => {
    setCommsForm(prev => {
      const current = prev[section] as Record<string, unknown>
      const nextSection: Record<string, unknown> = { ...current, [field]: value }
      if (field === "bot_token" && value.trim().length > 0 && "enabled" in current) {
        nextSection.enabled = true
      }
      return { ...prev, [section]: nextSection } as CommsForm
    })
  }, [])

  const handleCommsToggleChange = useCallback((section: keyof CommsForm, field: string, value: boolean) => {
    setCommsForm(prev => ({
      ...prev,
      [section]: { ...prev[section], [field]: value },
    }))
  }, [])

  const createGuardianTask = useCallback(async () => {
    if (!roomId) return
    setTaskSaving(true)
    setSettingsError("")
    try {
      const parsedArgs = taskArgs.trim() ? JSON.parse(taskArgs) : {}
      const res = await apiFetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          name: taskName.trim(),
          tool_name: taskToolName,
          schedule: taskSchedule.trim(),
          tool_args: parsedArgs,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Could not create Task Guardian job." }))
        setSettingsError(data.detail ?? "Could not create Task Guardian job.")
      } else {
        const created = await res.json()
        setTaskName("")
        notify(`Scheduled Task Guardian job **${created.name}**.`)
        await refreshControls()
      }
    } catch {
      setSettingsError("Task arguments must be valid JSON.")
    } finally {
      setTaskSaving(false)
    }
  }, [roomId, taskArgs, taskName, taskSchedule, taskToolName, refreshControls, notify])

  const setGuardianTaskState = useCallback(async (taskId: string, enabled: boolean) => {
    if (!roomId) return
    setSettingsError("")
    try {
      const res = await apiFetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ enabled }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Could not update Task Guardian job." }))
        setSettingsError(data.detail ?? "Could not update Task Guardian job.")
      } else {
        notify(`Task Guardian job ${enabled ? "**resumed**" : "**paused**"}.`)
        await refreshControls()
      }
    } catch {
      setSettingsError("Could not update Task Guardian job.")
    }
  }, [roomId, refreshControls, notify])

  const runGuardianTask = useCallback(async (taskId: string) => {
    if (!roomId) return
    setSettingsError("")
    try {
      const res = await apiFetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks/${taskId}/run`, {
        method: "POST",
        credentials: "include",
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Could not run Task Guardian job." }))
        setSettingsError(data.detail ?? "Could not run Task Guardian job.")
      } else {
        const data = await res.json()
        notify(`Task Guardian run finished with **${String(data.status ?? "unknown").toUpperCase()}**.`)
        await refreshControls()
      }
    } catch {
      setSettingsError("Could not run Task Guardian job.")
    }
  }, [roomId, refreshControls, notify])

  // ── Return ──────────────────────────────────────────────────────────────────
  return {
    // Loading / error
    settingsLoading, settingsError, setSettingsError,
    // Config
    modelsConfig, setModelsConfig, applyControlsConfig,
    // Token Guardian
    tokenGuardianMode, setTokenGuardianMode, savingTokenGuardianMode,
    saveTokenGuardianMode,
    // Default selection
    defaultSelection, setDefaultSelection,
    handleDefaultSelectionChange,
    savingDefaultSelection, saveDefaultSelection,
    // Routing policy
    routingPolicy, handleRoutingPolicyChange,
    // Local model
    localDefaultModel, handleLocalDefaultModelChange,
    // Agent overrides
    agentOverrides, handleAgentOverrideChange,
    savingAgentOverrides, saveAgentOverrides,
    savingModelSeats, saveModelSeats,
    // OpenRouter
    openRouterModels, loadingOpenRouterModels, openRouterLoadError,
    loadOpenRouterModels,
    // Ollama
    ollamaStatus, ollamaBaseUrl, setOllamaBaseUrl, ollamaLoading,
    checkOllamaStatus,
    // Model stack
    modelStack, handleModelStackChange,
    savingModelStack, saveModelStack,
    // Provider drafts
    providerDrafts, handleProviderDraftChange,
    savingProviderTokens, saveProviderTokens,
    // Comms
    commsForm, commsOpenSection, setCommsOpenSection,
    handleCommsTextChange, handleCommsToggleChange,
    savingComms, saveComms,
    // Policy / audit
    policyEntries,
    // Guardian tasks
    guardianTasks, guardianRuns,
    taskName, setTaskName, taskToolName, setTaskToolName,
    taskSchedule, setTaskSchedule, taskArgs, setTaskArgs,
    taskSaving, createGuardianTask, setGuardianTaskState, runGuardianTask,
    // Skills
    skills,
    // Room persona
    roomPersona, setRoomPersona, savingPersona, personaSaved, savePersona,
    // Room info
    roomInfo, setRoomInfo,
    // Guardian status
    guardianStatus, setGuardianStatus,
    // Dashboard
    controlsDashboard,
    // Execution gate
    savingExecution, executionSaved, executionError, toggleExecutionGate,
    securityProfile, setSecurityProfile, saveSecurityProfile,
    customGuardrails, setCustomGuardrails, saveCustomGuardrails,
    // PIN
    savingPin, pinSaved, pinError, saveOperatorPin,
    // Agents
    agents, setAgents, updateAgent,
    // Spawn agent
    spawnTemplate, setSpawnTemplate,
    spawnName, setSpawnName,
    spawnEmoji, setSpawnEmoji,
    spawnDescription, setSpawnDescription,
    spawnPrompt, setSpawnPrompt,
    spawning, spawnAgent,
    // Refresh
    refreshControls,
    // Constants
    LEGACY_COMMS_VISIBLE,
    AGENT_TEMPLATES,
    TASK_TOOL_OPTIONS,
    pageHasOpenRouterConfigured,
  }
}
