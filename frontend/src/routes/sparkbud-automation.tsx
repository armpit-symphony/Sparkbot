import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { hasChatSession } from "@/hooks/useAuth"

function SparkBudAutomation() {
  return <SparkBudPage budId="sb-automation" />
}

export const Route = createFileRoute("/sparkbud-automation")({
  component: SparkBudAutomation,
  beforeLoad: async () => {
    if (!hasChatSession()) {
      throw redirect({ to: "/login" })
    }
  },
})
