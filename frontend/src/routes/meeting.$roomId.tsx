import { createFileRoute, redirect } from "@tanstack/react-router"
import { hasChatSession } from "@/hooks/useAuth"
import MeetingRoomPage from "@/pages/MeetingRoomPage"
import { isV1LocalMode } from "@/lib/v1Local"

export const Route = createFileRoute("/meeting/$roomId")({
  component: MeetingRoomRoute,
  beforeLoad: async () => {
    if (!hasChatSession()) {
      throw redirect({ to: "/login" })
    }
    if (isV1LocalMode) {
      throw redirect({ to: "/dm" })
    }
  },
})

function MeetingRoomRoute() {
  const { roomId } = Route.useParams()
  return <MeetingRoomPage roomId={roomId} />
}
