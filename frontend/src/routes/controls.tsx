import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/controls")({
  beforeLoad: async () => {
    // Controls merged into Command Center — redirect to /spine
    throw redirect({ to: "/spine" })
  },
  component: () => null,
})
