import { hasChatSession } from "@/hooks/useAuth"
import { apiFetch } from "@/lib/apiBase"

const LOCAL_PASSPHRASE = "sparkbot-local"
const LOCAL_SESSION_KEY = "chat_auth"

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

export function isDesktopApp(): boolean {
  if (typeof window === "undefined") return false
  const proto = window.location.protocol
  return proto === "tauri:" || proto === "asset:" || window.location.origin === "null"
}

export const isV1LocalMode = import.meta.env.VITE_V1_LOCAL_MODE === "true"

export function isLocalDesktopMode(): boolean {
  return isDesktopApp() || isV1LocalMode
}

export async function ensureLocalChatSession(options?: {
  retries?: number
  retryDelayMs?: number
}): Promise<boolean> {
  if (typeof window === "undefined") return false
  if (hasChatSession()) return true
  if (!isLocalDesktopMode()) return false

  const retries = options?.retries ?? 20
  const retryDelayMs = options?.retryDelayMs ?? 750

  for (let attempt = 0; attempt < retries; attempt += 1) {
    try {
      const response = await apiFetch("/api/v1/chat/users/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ passphrase: LOCAL_PASSPHRASE }),
      })

      if (response.ok) {
        // Store the bearer token from the response body so apiFetch can inject it
        // as an Authorization header — required in the desktop build where the
        // cross-origin cookie (tauri.localhost → 127.0.0.1) is never sent by the browser.
        try {
          const data = await response.json()
          if (data?.access_token) {
            sessionStorage.setItem("chat_token", data.access_token)
          }
        } catch { /* non-fatal: bearer fallback unavailable */ }
        sessionStorage.setItem(LOCAL_SESSION_KEY, "1")
        return true
      }
    } catch {
      // The local backend may still be starting up. Retry below.
    }

    if (attempt < retries - 1) {
      await delay(retryDelayMs)
    }
  }

  return false
}
