import { createFileRoute, redirect } from "@tanstack/react-router"
import WorkstationPage from "@/pages/WorkstationPage"
import { hasChatSession } from "@/hooks/useAuth"
import { ensureLocalChatSession } from "@/lib/localSession"

export const Route = createFileRoute("/workstation")({
  component: WorkstationPage,
  beforeLoad: async () => {
    if (!hasChatSession() && !(await ensureLocalChatSession())) {
      throw redirect({ to: "/login" })
    }
  },
})
