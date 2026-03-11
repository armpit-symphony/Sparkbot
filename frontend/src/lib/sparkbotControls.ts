export const CONTROLS_ONBOARDING_KEY = "sparkbot_controls_onboarded"
export const CONTROLS_AUTOOPEN_KEY = "sparkbot_controls_autoshown"
export const CONTROLS_SEARCH_VALUE = "open"

export interface SparkbotControlsConfig {
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
    models: string[]
  }>
}

export interface ChatEntryTarget {
  to: "/dm"
  search?: {
    controls?: typeof CONTROLS_SEARCH_VALUE
  }
}

export function controlsOnboardingComplete(config: SparkbotControlsConfig | null): boolean {
  if (!config) return false
  const configuredProviders = config.providers.filter((provider) => provider.configured).length
  return configuredProviders > 0 && Boolean(config.stack.primary) && Boolean(config.stack.heavy_hitter)
}

export async function fetchControlsConfig(): Promise<SparkbotControlsConfig | null> {
  try {
    const response = await fetch("/api/v1/chat/models/config", {
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
