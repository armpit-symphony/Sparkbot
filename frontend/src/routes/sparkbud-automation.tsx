import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { isLoggedIn } from "@/hooks/useAuth"

function SparkBudAutomation() {
  return <SparkBudPage budId="sb-automation" />
}

export const Route = createFileRoute("/sparkbud-automation")({
  component: SparkBudAutomation,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})
