import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { hasChatSession } from "@/hooks/useAuth"
import { ensureLocalChatSession, isLocalDesktopMode } from "@/lib/localSession"

function SparkBudWebmaker() {
  return <SparkBudPage budId="sb-webmaker" />
}

export const Route = createFileRoute("/sparkbud-webmaker")({
  component: SparkBudWebmaker,
  beforeLoad: async () => {
    if (!hasChatSession() && !(await ensureLocalChatSession())) {
      throw redirect({ to: "/login" })
    }
    if (isLocalDesktopMode()) {
      throw redirect({ to: "/dm" })
    }
  },
})
