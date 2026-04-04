import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { hasChatSession } from "@/hooks/useAuth"
import { ensureLocalChatSession, isLocalDesktopMode } from "@/lib/localSession"

function SparkBudResearch() {
  return <SparkBudPage budId="sb-research" />
}

export const Route = createFileRoute("/sparkbud-research")({
  component: SparkBudResearch,
  beforeLoad: async () => {
    if (!hasChatSession() && !(await ensureLocalChatSession())) {
      throw redirect({ to: "/login" })
    }
    if (isLocalDesktopMode()) {
      throw redirect({ to: "/dm" })
    }
  },
})
