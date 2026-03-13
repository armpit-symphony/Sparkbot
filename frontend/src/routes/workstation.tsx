import { createFileRoute, redirect } from "@tanstack/react-router"
import WorkstationPage from "@/pages/WorkstationPage"
import { hasChatSession } from "@/hooks/useAuth"
import { isV1LocalMode } from "@/lib/v1Local"

export const Route = createFileRoute("/workstation")({
  component: WorkstationPage,
  beforeLoad: async () => {
    if (!hasChatSession()) {
      throw redirect({ to: "/login" })
    }
    if (isV1LocalMode) {
      throw redirect({ to: "/dm" })
    }
  },
})
