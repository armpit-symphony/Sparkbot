import { createFileRoute, redirect } from "@tanstack/react-router"
import WorkstationPage from "@/pages/WorkstationPage"
import { hasChatSession } from "@/hooks/useAuth"

export const Route = createFileRoute("/workstation")({
  component: WorkstationPage,
  beforeLoad: async () => {
    if (!hasChatSession()) {
      throw redirect({ to: "/login" })
    }
  },
})
