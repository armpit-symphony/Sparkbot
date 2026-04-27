import { Link, createFileRoute } from "@tanstack/react-router"

import ChangePassword from "@/components/UserSettings/ChangePassword"
import DeleteAccount from "@/components/UserSettings/DeleteAccount"
import UserInformation from "@/components/UserSettings/UserInformation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth from "@/hooks/useAuth"

const tabsConfig = [
  { value: "my-profile", title: "My profile", component: UserInformation },
  { value: "password", title: "Password", component: ChangePassword },
  { value: "danger-zone", title: "Danger zone", component: DeleteAccount },
]

function SparkbotOpsSettings() {
  const readinessItems = [
    "Computer Control, operator PIN setup, and approval visibility are room-scoped and exposed in Sparkbot DM controls.",
    "Task Guardian can schedule approved read-only recurring work such as inbox digests and diagnostics.",
    "Policy decisions and tool actions are audited for review before broader consumer rollout.",
    "Next launch work: onboarding copy, friendlier first-run defaults, and admin polish for non-technical users.",
  ]

  return (
    <div className="space-y-4">
      <div className="rounded-xl border p-4">
        <h2 className="text-lg font-semibold">Sparkbot Ops</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Consumer readiness status and the live control surface for room automation.
        </p>
      </div>

      <div className="rounded-xl border p-4">
        <h3 className="text-sm font-semibold">Current readiness</h3>
        <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
          {readinessItems.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="mt-0.5 text-primary">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-xl border p-4">
        <h3 className="text-sm font-semibold">Where to manage it</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Open Sparkbot DM and use the gear icon in the header to manage Computer Control, the operator PIN, recent approval decisions,
          and Task Guardian schedules for the room.
        </p>
        <div className="mt-3">
          <Link
            to="/dm"
            className="inline-flex rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90"
          >
            Open Sparkbot Controls
          </Link>
        </div>
      </div>
    </div>
  )
}

export const Route = createFileRoute("/_layout/settings")({
  component: UserSettings,
  head: () => ({
    meta: [
      {
        title: "Settings - FastAPI Template",
      },
    ],
  }),
})

function UserSettings() {
  const { user: currentUser } = useAuth()
  const finalTabs = currentUser?.is_superuser
    ? [...tabsConfig, { value: "sparkbot-ops", title: "Sparkbot ops", component: SparkbotOpsSettings }]
    : tabsConfig

  if (!currentUser) {
    return null
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">User Settings</h1>
        <p className="text-muted-foreground">
          Manage your account settings and preferences
        </p>
      </div>

      <Tabs defaultValue="my-profile">
        <TabsList>
          {finalTabs.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              {tab.title}
            </TabsTrigger>
          ))}
        </TabsList>
        {finalTabs.map((tab) => (
          <TabsContent key={tab.value} value={tab.value}>
            <tab.component />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
