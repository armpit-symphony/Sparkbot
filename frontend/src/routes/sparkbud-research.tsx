import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { isLoggedIn } from "@/hooks/useAuth"

function SparkBudResearch() {
  return <SparkBudPage budId="sb-research" />
}

export const Route = createFileRoute("/sparkbud-research")({
  component: SparkBudResearch,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})
