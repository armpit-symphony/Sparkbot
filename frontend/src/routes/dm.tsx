// DM route - redirects to Sparkbot DM

import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { hasChatSession } from "@/hooks/useAuth"
import SparkbotDmPage from "@/pages/SparkbotDmPage"
import { CONTROLS_SEARCH_VALUE } from "@/lib/sparkbotControls"
import { isV1LocalMode } from "@/lib/v1Local"
import { apiFetch } from "@/lib/apiBase"

const searchSchema = z.object({
  controls: z.literal(CONTROLS_SEARCH_VALUE).optional().catch(undefined),
})

export const Route = createFileRoute("/dm")({
  validateSearch: searchSchema,
  beforeLoad: async () => {
    if (hasChatSession()) return
    // In V1 desktop mode the passphrase is fixed — auto-login so the user
    // never sees the passphrase screen.
    if (isV1LocalMode) {
      try {
        const res = await apiFetch("/api/v1/chat/users/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ passphrase: "sparkbot-local" }),
        })
        if (res.ok) {
          sessionStorage.setItem("chat_auth", "1")
          return // proceed to SparkbotDmPage
        }
      } catch {
        // fall through to login page if backend is not yet ready
      }
    }
    throw redirect({ to: "/login" })
  },
  component: SparkbotDmPage,
})
