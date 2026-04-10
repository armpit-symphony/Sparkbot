// Legacy chat route component. V1 local desktop builds are redirected to /dm.

import { createFileRoute, redirect } from "@tanstack/react-router"
import ChatPage from "@/pages/ChatPage"
import { isV1LocalMode } from "@/lib/v1Local"

export const Route = createFileRoute("/_layout/chat")({
  beforeLoad: () => {
    if (isV1LocalMode) {
      throw redirect({ to: "/dm" })
    }
  },
  component: ChatPage,
  head: () => ({
    meta: [
      {
        title: "Legacy Chat - Sparkbot",
      },
    ],
  }),
})

export default ChatPage
