import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { hasChatSession } from "@/hooks/useAuth"
import { isV1LocalMode } from "@/lib/v1Local"

function SparkBudResearch() {
  return <SparkBudPage budId="sb-research" />
}

export const Route = createFileRoute("/sparkbud-research")({
  component: SparkBudResearch,
  beforeLoad: async () => {
    if (!hasChatSession()) {
      throw redirect({ to: "/login" })
    }
    if (isV1LocalMode) {
      throw redirect({ to: "/dm" })
    }
  },
})
