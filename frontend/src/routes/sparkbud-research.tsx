import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { hasChatSession } from "@/hooks/useAuth"

function SparkBudResearch() {
  return <SparkBudPage budId="sb-research" />
}

export const Route = createFileRoute("/sparkbud-research")({
  component: SparkBudResearch,
  beforeLoad: async () => {
    if (!hasChatSession()) {
      throw redirect({ to: "/login" })
    }
  },
})
