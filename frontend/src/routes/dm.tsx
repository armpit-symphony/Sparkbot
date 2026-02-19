// DM route - redirects to Sparkbot DM

import { createFileRoute } from "@tanstack/react-router"
import SparkbotDmPage from "@/pages/SparkbotDmPage"

export const Route = createFileRoute("/dm")({
  component: SparkbotDmPage,
})

export default SparkbotDmPage
