const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1"])
const DEFAULT_DESKTOP_API_BASE = "http://127.0.0.1:8000"
const DESKTOP_HOSTS = new Set(["tauri.localhost"])

function normalizeBase(value: string | undefined | null): string {
  return (value ?? "").trim().replace(/\/+$/, "")
}

function hasWindow(): boolean {
  return typeof window !== "undefined"
}

function isDesktopProtocol(protocol: string): boolean {
  return protocol === "tauri:" || protocol === "asset:"
}

function isDesktopHost(hostname: string): boolean {
  return DESKTOP_HOSTS.has(hostname) || hostname.endsWith(".tauri.localhost")
}

export function getApiBase(): string {
  const configuredBase = normalizeBase(import.meta.env.VITE_API_URL)

  if (!hasWindow()) {
    return configuredBase
  }

  const { hostname, origin, protocol } = window.location
  if (isDesktopProtocol(protocol) || origin === "null" || isDesktopHost(hostname)) {
    return configuredBase || DEFAULT_DESKTOP_API_BASE
  }

  if (!configuredBase) {
    return ""
  }

  try {
    const configuredUrl = new URL(configuredBase)
    const configuredIsLocal = LOCAL_HOSTS.has(configuredUrl.hostname)
    const currentIsLocal = LOCAL_HOSTS.has(hostname)

    // Hosted web builds should stay same-origin even if a local dev API URL was
    // accidentally baked into the bundle.
    if (configuredIsLocal && !currentIsLocal) {
      return ""
    }

    if (configuredUrl.origin === origin) {
      return ""
    }
  } catch {
    return configuredBase
  }

  return configuredBase
}

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path
  }
  const normalizedPath = path.startsWith("/") ? path : `/${path}`
  const base = getApiBase()
  return base ? `${base}${normalizedPath}` : normalizedPath
}

export function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(input), init)
}

export function apiWebSocketUrl(path: string): string {
  if (/^wss?:\/\//i.test(path)) {
    return path
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`
  const base = getApiBase()

  if (!base) {
    if (!hasWindow()) {
      return normalizedPath
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
    return `${protocol}//${window.location.host}${normalizedPath}`
  }

  const httpUrl = new URL(base)
  httpUrl.protocol = httpUrl.protocol === "https:" ? "wss:" : "ws:"
  httpUrl.pathname = normalizedPath
  httpUrl.search = ""
  httpUrl.hash = ""
  return httpUrl.toString()
}
