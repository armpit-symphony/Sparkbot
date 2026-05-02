import { createFileRoute, redirect } from "@tanstack/react-router"
import { hasChatSession } from "@/hooks/useAuth"
import { ensureLocalChatSession } from "@/lib/localSession"
import SparkbotDmPage from "@/pages/SparkbotDmPage"

function ControlsPage() {
  return <SparkbotDmPage controlsSurface />
}

export const Route = createFileRoute("/controls")({
  beforeLoad: async () => {
    if (hasChatSession()) return
    if (await ensureLocalChatSession()) return
    throw redirect({ to: "/login" })
  },
  component: ControlsPage,
})
