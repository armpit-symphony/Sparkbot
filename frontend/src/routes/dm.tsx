// DM route - redirects to Sparkbot DM

import { createFileRoute, redirect } from "@tanstack/react-router"
import { z } from "zod"
import { hasChatSession } from "@/hooks/useAuth"
import SparkbotDmPage from "@/pages/SparkbotDmPage"
import { CONTROLS_SEARCH_VALUE } from "@/lib/sparkbotControls"

const searchSchema = z.object({
  controls: z.literal(CONTROLS_SEARCH_VALUE).optional().catch(undefined),
})

export const Route = createFileRoute("/dm")({
  validateSearch: searchSchema,
  beforeLoad: async () => {
    if (!hasChatSession()) {
      throw redirect({ to: "/login" })
    }
  },
  component: SparkbotDmPage,
})
