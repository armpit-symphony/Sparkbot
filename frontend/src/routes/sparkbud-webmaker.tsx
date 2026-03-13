import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { hasChatSession } from "@/hooks/useAuth"
import { isV1LocalMode } from "@/lib/v1Local"

function SparkBudWebmaker() {
  return <SparkBudPage budId="sb-webmaker" />
}

export const Route = createFileRoute("/sparkbud-webmaker")({
  component: SparkBudWebmaker,
  beforeLoad: async () => {
    if (!hasChatSession()) {
      throw redirect({ to: "/login" })
    }
    if (isV1LocalMode) {
      throw redirect({ to: "/dm" })
    }
  },
})
