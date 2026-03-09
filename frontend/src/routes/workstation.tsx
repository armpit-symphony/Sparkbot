import { createFileRoute, redirect } from "@tanstack/react-router"
import WorkstationPage from "@/pages/WorkstationPage"
import { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/workstation")({
  component: WorkstationPage,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})
