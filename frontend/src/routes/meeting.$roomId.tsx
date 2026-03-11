import { createFileRoute, redirect } from "@tanstack/react-router"
import { hasChatSession } from "@/hooks/useAuth"
import MeetingRoomPage from "@/pages/MeetingRoomPage"

export const Route = createFileRoute("/meeting/$roomId")({
  component: MeetingRoomRoute,
  beforeLoad: async () => {
    if (!hasChatSession()) {
      throw redirect({ to: "/login" })
    }
  },
})

function MeetingRoomRoute() {
  const { roomId } = Route.useParams()
  return <MeetingRoomPage roomId={roomId} />
}
