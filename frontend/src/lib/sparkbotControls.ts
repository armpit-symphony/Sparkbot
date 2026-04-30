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
  routing_policy?: {
    default_provider_authoritative: boolean
    cross_provider_fallback: boolean
  }
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
