// Legacy chat route. Public Sparkbot uses /dm as the primary chat surface.

import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/chat")({
  beforeLoad: () => {
    throw redirect({ to: "/dm" })
  },
  component: () => null,
  head: () => ({
    meta: [
      {
        title: "Legacy Chat - Sparkbot",
      },
    ],
  }),
})
