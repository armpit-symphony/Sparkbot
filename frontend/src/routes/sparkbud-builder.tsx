import { createFileRoute, redirect } from "@tanstack/react-router"
import SparkBudPage from "@/pages/SparkBudPage"
import { isLoggedIn } from "@/hooks/useAuth"

function SparkBudBuilder() {
  return <SparkBudPage budId="sb-builder" />
}

export const Route = createFileRoute("/sparkbud-builder")({
  component: SparkBudBuilder,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({ to: "/login" })
    }
  },
})
