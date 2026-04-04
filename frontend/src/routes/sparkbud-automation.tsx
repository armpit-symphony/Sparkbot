import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { hasChatSession } from "@/hooks/useAuth"
import { ensureLocalChatSession, isLocalDesktopMode } from "@/lib/localSession"

function SparkBudAutomation() {
  return <SparkBudPage budId="sb-automation" />
}

export const Route = createFileRoute("/sparkbud-automation")({
  component: SparkBudAutomation,
  beforeLoad: async () => {
    if (!hasChatSession() && !(await ensureLocalChatSession())) {
      throw redirect({ to: "/login" })
    }
    if (isLocalDesktopMode()) {
      throw redirect({ to: "/dm" })
    }
  },
})
