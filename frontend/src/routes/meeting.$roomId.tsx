import { createFileRoute, redirect } from "@tanstack/react-router"
import { hasChatSession } from "@/hooks/useAuth"
import { ensureLocalChatSession, isLocalDesktopMode } from "@/lib/localSession"
import MeetingRoomPage from "@/pages/MeetingRoomPage"

export const Route = createFileRoute("/meeting/$roomId")({
  component: MeetingRoomRoute,
  beforeLoad: async () => {
    if (!hasChatSession() && !(await ensureLocalChatSession())) {
      throw redirect({ to: "/login" })
    }
    if (isLocalDesktopMode()) {
      throw redirect({ to: "/dm" })
    }
  },
})

function MeetingRoomRoute() {
  const { roomId } = Route.useParams()
  return <MeetingRoomPage roomId={roomId} />
}
