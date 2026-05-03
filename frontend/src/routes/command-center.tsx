import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/command-center")({
  beforeLoad: () => {
    throw redirect({ to: "/spine" })
  },
})
