import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { hasChatSession } from "@/hooks/useAuth"
import { ensureLocalChatSession, isLocalDesktopMode } from "@/lib/localSession"

function SparkBudBuilder() {
  return <SparkBudPage budId="sb-builder" />
}

export const Route = createFileRoute("/sparkbud-builder")({
  component: SparkBudBuilder,
  beforeLoad: async () => {
    if (!hasChatSession() && !(await ensureLocalChatSession())) {
      throw redirect({ to: "/login" })
    }
    if (isLocalDesktopMode()) {
      throw redirect({ to: "/dm" })
    }
  },
})
