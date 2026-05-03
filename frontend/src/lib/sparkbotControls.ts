import { apiFetch } from "@/lib/apiBase"

export const CONTROLS_ONBOARDING_KEY = "sparkbot_controls_onboarded"
export const CONTROLS_AUTOOPEN_KEY = "sparkbot_controls_autoshown"
export const CONTROLS_SEARCH_VALUE = "open"

export interface SparkbotControlsConfig {
  active_model: string
  stack: {
    primary: string
    backup_1: string
    backup_2: string
    heavy_hitter: string
  }
  default_selection: {
    provider: string
    model: string
    label?: string
  }
  local_runtime: {
    default_local_model: string
    base_url: string
  }
  model_labels?: Record<string, string>
  routing_policy?: {
    default_provider_authoritative: boolean
    cross_provider_fallback: boolean
  }
  token_guardian_mode?: string
  global_computer_control?: boolean
  global_computer_control_expires_at?: number | null
  global_computer_control_ttl_remaining?: number | null
  agent_overrides: Record<
    string,
    {
      route: string
      model?: string
    }
  >
  available_agents: Array<{
    name: string
    emoji: string
    description: string
    is_builtin?: boolean
    identity?: Record<string, unknown>
  }>
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
  ollama_status?: {
    reachable: boolean
    base_url: string
    models: string[]
    model_ids?: string[]
    models_available?: boolean
  }
}

export interface ControlsModelOption {
  id: string
  label: string
}

export interface ControlsModelGroup {
  id: string
  label: string
  models: ControlsModelOption[]
}

export interface ChatEntryTarget {
  to: "/dm"
  search?: {
    controls?: typeof CONTROLS_SEARCH_VALUE
  }
}

export function controlsOnboardingComplete(config: SparkbotControlsConfig | null): boolean {
  if (!config) return false
  const defaultModel = config.default_selection?.model || config.active_model
  if (!defaultModel) return false
  const providerId = providerForModel(defaultModel)
  const provider = config.providers.find((item) => item.id === providerId)
  if (!provider) return false
  return provider.configured || provider.models_available === true
}

export function providerForModel(model: string): string {
  if (model.startsWith("openrouter/")) return "openrouter"
  if (model.startsWith("ollama/")) return "ollama"
  if (model.startsWith("gpt-") || model.startsWith("codex-")) return "openai"
  if (model.startsWith("claude")) return "anthropic"
  if (model.startsWith("gemini/")) return "google"
  if (model.startsWith("groq/")) return "groq"
  if (model.startsWith("minimax/")) return "minimax"
  if (model.startsWith("xai/")) return "xai"
  return "other"
}

export function routeForModelOverride(model: string): string {
  const provider = providerForModel(model)
  if (provider === "ollama") return "local"
  if (["openrouter", "openai", "anthropic", "google", "groq", "minimax", "xai"].includes(provider)) {
    return provider
  }
  return "default"
}

export function agentDisplayName(name: string): string {
  if (name === "sparkbot") return "Sparkbot"
  return name
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

export function buildControlsModelGroups(
  config: SparkbotControlsConfig | null,
): ControlsModelGroup[] {
  if (!config) return []

  const localModels = [
    config.local_runtime?.default_local_model,
    ...(config.ollama_status?.model_ids ?? []),
    ...(config.ollama_status?.models ?? []).map((modelName) =>
      modelName.startsWith("ollama/") ? modelName : `ollama/${modelName}`,
    ),
  ].filter(Boolean) as string[]

  const modelIds = Array.from(
    new Set(
      [
        config.active_model,
        config.default_selection?.model,
        config.stack?.primary,
        config.stack?.backup_1,
        config.stack?.backup_2,
        config.stack?.heavy_hitter,
        ...Object.keys(config.model_labels ?? {}),
        ...localModels,
        ...(config.providers ?? []).flatMap((provider) => [
          ...(provider.available_models ?? []),
          ...(provider.models ?? []),
        ]),
      ].filter(Boolean) as string[],
    ),
  )

  const labelForModel = (modelId: string) =>
    config.model_labels?.[modelId] ?? modelId.replace("ollama/", "")

  const providerGroups: Array<{ id: string; label: string }> = [
    { id: "openrouter", label: "OpenRouter" },
    { id: "openai", label: "OpenAI" },
    { id: "anthropic", label: "Anthropic" },
    { id: "google", label: "Google" },
    { id: "groq", label: "Groq" },
    { id: "minimax", label: "MiniMax" },
    { id: "xai", label: "xAI" },
    { id: "ollama", label: "Local (Ollama)" },
    { id: "other", label: "Other configured models" },
  ]

  return providerGroups
    .map((group) => ({
      id: group.id,
      label: group.label,
      models: modelIds
        .filter((modelId) => providerForModel(modelId) === group.id)
        .map((modelId) => ({ id: modelId, label: labelForModel(modelId) })),
    }))
    .filter((group) => group.models.length > 0)
}

export async function fetchControlsConfig(): Promise<SparkbotControlsConfig | null> {
  try {
    const response = await apiFetch("/api/v1/chat/models/config", {
      credentials: "include",
    })
    if (!response.ok) return null
    return (await response.json()) as SparkbotControlsConfig
  } catch {
    return null
  }
}

export async function resolveChatEntryTarget(): Promise<ChatEntryTarget> {
  const config = await fetchControlsConfig()
  if (!controlsOnboardingComplete(config)) {
    return {
      to: "/dm",
      search: { controls: CONTROLS_SEARCH_VALUE },
    }
  }
  return { to: "/dm" }
}

export function buildChatEntryHref(target: ChatEntryTarget): string {
  if (!target.search?.controls) return target.to
  const params = new URLSearchParams()
  params.set("controls", target.search.controls)
  return `${target.to}?${params.toString()}`
}

export function isControlsSearchOpen(search: string): boolean {
  return new URLSearchParams(search).get("controls") === CONTROLS_SEARCH_VALUE
}
