import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { isLoggedIn } from "@/hooks/useAuth"

function SparkBudWebmaker() {
  return <SparkBudPage budId="sb-webmaker" />
}

export const Route = createFileRoute("/sparkbud-webmaker")({
  component: SparkBudWebmaker,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})
