import { Link, createFileRoute } from "@tanstack/react-router"
import {
  ArrowRight,
  Bot,
  CalendarDays,
  Clock3,
  Database,
  LoaderCircle,
  Mail,
  MessageSquareText,
  Radar,
  ShieldCheck,
  Sparkles,
  SquareCheckBig,
  Waves,
} from "lucide-react"
import { useEffect, useState } from "react"

import {
  type SpineEventsResult,
  type SpineTMOverview,
  fetchSpineRecentEvents,
  fetchSpineTMOverview,
} from "@/lib/spine"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "Command Center - Sparkbot",
      },
    ],
  }),
})

const moduleCards = [
  {
    title: "Meetings",
    description: "Prep notes, live capture, decisions, and automatic follow-up drafts.",
    icon: CalendarDays,
  },
  {
    title: "Inbox",
    description: "Important email, draft replies, waiting-fors, and batched approvals.",
    icon: Mail,
  },
  {
    title: "Conversations",
    description: "Sparkbot DM, room context, linked channels, and recent assistant activity.",
    icon: MessageSquareText,
  },
  {
    title: "Automation",
    description: "Recurring jobs, triggers, scheduled actions, and proactive nudges.",
    icon: Radar,
  },
]

const systemSignals = [
  "FastAPI remains the main control plane for the connected Sparkbot instance.",
  "Dashboard will aggregate reminders, jobs, approvals, inbox, and meetings in one surface.",
  "Telegram, Discord, and WhatsApp stay linked channels under the same account and room model.",
]

type DashboardSummaryData = {
  generated_at: string
  summary: {
    rooms_count: number
    execution_enabled_rooms: number
    open_tasks: number
    tasks_due_today: number
    pending_reminders: number
    reminders_due_today: number
    pending_approvals: number
    guardian_jobs: number
    guardian_jobs_enabled: number
    task_guardian_enabled: boolean
    token_guardian_mode: string
  }
  today: {
    rooms: Array<{
      id: string
      name: string
      execution_allowed: boolean
      updated_at: string
    }>
    upcoming_reminders: Array<{
      id: string
      room_id: string
      room_name: string
      message: string
      fire_at: string
      recurrence: string
    }>
    focus_tasks: Array<{
      id: string
      room_id: string
      room_name: string
      title: string
      status: string
      due_date: string | null
      assigned_to: string | null
    }>
    approval_requests: Array<{
      id: string
      room_id: string | null
      room_name: string
      created_at: string
      expires_at: string
      tool_name: string
      reason: string
      tool_args_preview: string
    }>
    guardian_jobs: Array<{
      id: string
      room_id: string
      room_name: string
      name: string
      tool_name: string
      schedule: string
      enabled: boolean
      next_run_at: string | null
      last_status: string | null
    }>
    meetings: Array<{
      id: string
      room_id: string
      room_name: string
      type: string
      created_at: string
      excerpt: string
    }>
    inbox: {
      configured: boolean
      source: string
      summary_text: string
    }
    token_guardian: {
      mode: string
      live_ready: boolean
      configured_models: string[]
      allowed_live_models: string[]
      total_tokens: number
      total_cost: number
      requests: number
      live_routes_24h: number
      suggested_switches_24h: number
      estimated_savings_24h: number
      top_models: Array<{
        model: string
        tokens: number
      }>
      last_route: {
        created_at: string
        classification: string | null
        current_model: string | null
        selected_model: string | null
        applied_model: string | null
        fallback_reason: string | null
        live_routed: boolean
        would_switch_models: boolean
      } | null
    }
  }
}

function formatRelativeTime(value: string | null | undefined) {
  if (!value) return "—"
  try {
    const diff = Date.now() - new Date(value).getTime()
    const s = Math.floor(diff / 1000)
    if (s < 60) return `${s}s ago`
    if (s < 3600) return `${Math.floor(s / 60)}m ago`
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`
    return `${Math.floor(s / 86400)}d ago`
  } catch {
    return value
  }
}

function SpineWorkStateSection() {
  const [snapshot, setSnapshot] = useState<SpineTMOverview | null>(null)
  const [events, setEvents] = useState<SpineEventsResult | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.allSettled([fetchSpineTMOverview(5), fetchSpineRecentEvents(5)]).then(([ovResult, evResult]) => {
      if (ovResult.status === "fulfilled") setSnapshot(ovResult.value)
      if (evResult.status === "fulfilled") setEvents(evResult.value)
      setLoading(false)
    })
  }, [])

  const stats = [
    { label: "Open", count: snapshot?.open_queue.length ?? 0, highlight: false },
    { label: "Blocked", count: snapshot?.blocked_queue.length ?? 0, highlight: true },
    { label: "↑Approval", count: snapshot?.approval_waiting_queue.length ?? 0, highlight: true },
    { label: "Stale", count: snapshot?.stale_queue.length ?? 0, highlight: false },
    { label: "Orphaned", count: snapshot?.orphan_queue.length ?? 0, highlight: false },
    { label: "Resurfaced", count: snapshot?.recently_resurfaced_queue.length ?? 0, highlight: false },
    { label: "Ready", count: snapshot?.assignment_ready_queue.length ?? 0, highlight: false },
  ]

  const attentionTasks = [
    ...(snapshot?.blocked_queue ?? []),
    ...(snapshot?.approval_waiting_queue ?? []),
  ].slice(0, 5)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-medium text-primary">
            <Database className="size-4" />
            Guardian Spine · Work State
          </div>
          <Link
            to="/spine"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            Open Spine Ops <ArrowRight className="size-3" />
          </Link>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin" /> Loading Spine…
          </div>
        ) : (
          <>
            {/* Stat pills */}
            <div className="flex flex-wrap gap-2">
              {stats.map(({ label, count, highlight }) => (
                <div
                  key={label}
                  className={`rounded-lg border px-2.5 py-1 text-xs font-medium ${highlight && count > 0 ? "border-destructive/40 bg-destructive/5 text-destructive" : "text-muted-foreground"}`}
                >
                  {label}: {count}
                </div>
              ))}
            </div>

            {/* Needs attention */}
            {attentionTasks.length > 0 && (
              <div className="space-y-1">
                <div className="text-xs font-semibold text-muted-foreground">Needs attention</div>
                {attentionTasks.map((task) => (
                  <div key={task.task_id} className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="min-w-0 flex-1 truncate">{task.title || task.task_id}</span>
                    <span
                      className={`rounded border px-1.5 py-0.5 text-xs ${task.status === "blocked" ? "border-destructive/40 text-destructive" : "border-yellow-400/40 text-yellow-600 dark:text-yellow-400"}`}
                    >
                      {task.status}
                    </span>
                    {task.room_id && (
                      <span className="max-w-[100px] truncate text-xs text-muted-foreground">{task.room_id}</span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Recent events */}
            {events && events.events.length > 0 && (
              <div className="space-y-1">
                <div className="text-xs font-semibold text-muted-foreground">Recent events</div>
                {events.events.map((e) => (
                  <div key={e.event_id} className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">
                      {e.event_type.replace(/_/g, " ")}
                    </span>
                    <span>{e.subsystem}</span>
                    {e.task_id && <span className="max-w-[100px] truncate">{e.task_id}</span>}
                    <span className="ml-auto">{formatRelativeTime(e.occurred_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) {
    return "No schedule"
  }
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(value))
  } catch {
    return value
  }
}

function formatMoney(value: number | null | undefined) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value ?? 0)
}

function Dashboard() {
  const { user: currentUser } = useAuth()
  const firstName = currentUser?.full_name?.split(" ")[0] || currentUser?.email?.split("@")[0] || "there"
  const [dashboard, setDashboard] = useState<DashboardSummaryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [actioningApprovalId, setActioningApprovalId] = useState<string | null>(null)

  async function refreshDashboard() {
    try {
      setLoading(true)
      setError("")
      const res = await fetch("/api/v1/chat/dashboard/summary", {
        credentials: "include",
      })
      if (!res.ok) {
        throw new Error(`Dashboard request failed (${res.status})`)
      }
      const data = (await res.json()) as DashboardSummaryData
      setDashboard(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshDashboard()
  }, [])

  async function handleApprovalAction(confirmId: string, action: "approve" | "deny") {
    try {
      setActioningApprovalId(confirmId)
      setError("")
      const res = await fetch(`/api/v1/chat/dashboard/approvals/${confirmId}/${action}`, {
        method: "POST",
        credentials: "include",
      })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(body || `Approval ${action} failed (${res.status})`)
      }
      await refreshDashboard()
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${action} approval`)
    } finally {
      setActioningApprovalId(null)
    }
  }

  const priorityCards = [
    {
      title: "Today Brief",
      description: `${dashboard?.summary.reminders_due_today ?? 0} reminders due today and ${dashboard?.summary.tasks_due_today ?? 0} tasks needing attention.`,
      status: loading ? "Loading" : "Live",
      icon: Clock3,
    },
    {
      title: "Action Queue",
      description: `${dashboard?.summary.pending_approvals ?? 0} durable pending approvals waiting for confirmation.`,
      status: dashboard?.today.approval_requests.length ? "Live" : "Quiet",
      icon: SquareCheckBig,
    },
    {
      title: "Guardian Ops",
      description: `${dashboard?.summary.guardian_jobs_enabled ?? 0}/${dashboard?.summary.guardian_jobs ?? 0} Task Guardian jobs enabled.`,
      status: dashboard?.summary.token_guardian_mode === "live" ? "Live routing" : dashboard?.summary.task_guardian_enabled ? "Active" : "Off",
      icon: ShieldCheck,
    },
  ]

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-3xl border bg-gradient-to-br from-primary/15 via-background to-chart-2/10 p-6 shadow-sm md:p-8">
        <div
          className="pointer-events-none absolute inset-y-0 right-0 hidden w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.18),transparent_52%)] dark:bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.08),transparent_52%)] md:block"
          aria-hidden="true"
        />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-4">
            <Badge variant="secondary" className="gap-1.5 rounded-full px-3 py-1">
              <Sparkles className="size-3.5" />
              Command Center beta
            </Badge>
            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
                Good to see you, {firstName}.
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-muted-foreground md:text-base">
                This is the new home surface for Sparkbot as a personal assistant and office worker.
                It will become the place where your day, approvals, automations, inbox, meetings,
                and Guardian status are visible at a glance.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="rounded-full px-3 py-1">FastAPI main surface</Badge>
              <Badge variant="outline" className="rounded-full px-3 py-1">Desktop-friendly</Badge>
              <Badge variant="outline" className="rounded-full px-3 py-1">Consumer + operator UX</Badge>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Link
              to="/dm"
              className="inline-flex min-w-44 items-center justify-between rounded-2xl border bg-background/80 px-4 py-3 text-sm font-medium shadow-sm transition hover:bg-background"
            >
              Open Sparkbot DM
              <ArrowRight className="size-4 text-muted-foreground" />
            </Link>
            <Link
              to="/settings"
              className="inline-flex min-w-44 items-center justify-between rounded-2xl border bg-background/50 px-4 py-3 text-sm font-medium transition hover:bg-background/80"
            >
              Open settings
              <ArrowRight className="size-4 text-muted-foreground" />
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          {
            title: "Rooms",
            value: dashboard?.summary.rooms_count ?? 0,
            detail: `${dashboard?.summary.execution_enabled_rooms ?? 0} execution-enabled`,
          },
          {
            title: "Open tasks",
            value: dashboard?.summary.open_tasks ?? 0,
            detail: `${dashboard?.summary.tasks_due_today ?? 0} due today`,
          },
          {
            title: "Pending reminders",
            value: dashboard?.summary.pending_reminders ?? 0,
            detail: `${dashboard?.summary.reminders_due_today ?? 0} due today`,
          },
          {
            title: "Approval requests",
            value: dashboard?.summary.pending_approvals ?? 0,
            detail: "Durable pending queue",
          },
        ].map((item) => (
          <Card key={item.title}>
            <CardHeader className="gap-1">
              <CardDescription>{item.title}</CardDescription>
              <CardTitle className="text-3xl">{item.value}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">{item.detail}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
        <Card className="border-primary/20">
          <CardHeader className="gap-3">
            <div className="flex items-center gap-2 text-sm font-medium text-primary">
              <Bot className="size-4" />
              What this dashboard becomes
            </div>
            <CardTitle className="text-2xl">Main command center</CardTitle>
            <CardDescription className="max-w-2xl text-sm leading-6">
              Sparkbot should open to an operational overview, not a blank template. This shell
              establishes the landing zone for daily briefings, personal task flow, office work,
              and Guardian oversight.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            {priorityCards.map((card) => (
              <div key={card.title} className="rounded-2xl border bg-background/70 p-4">
                <div className="mb-3 flex items-center justify-between">
                  <card.icon className="size-4 text-primary" />
                  <Badge variant={card.status === "Shell ready" ? "default" : "outline"}>
                    {card.status}
                  </Badge>
                </div>
                <h2 className="text-sm font-semibold">{card.title}</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{card.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">System direction</CardTitle>
            <CardDescription>
              The existing live stack stays intact while the dashboard grows around it.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {systemSignals.map((item) => (
              <div key={item} className="flex gap-3 rounded-2xl border px-4 py-3">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" />
                <p className="text-sm leading-6 text-muted-foreground">{item}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Today brief</CardTitle>
            <CardDescription>
              Live reminders, tasks, and the real pending approvals queue.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-3">
              <div className="text-sm font-semibold">Upcoming reminders</div>
              {loading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <LoaderCircle className="size-4 animate-spin" />
                  Loading reminders
                </div>
              ) : dashboard?.today.upcoming_reminders.length ? (
                dashboard.today.upcoming_reminders.map((reminder) => (
                  <div key={reminder.id} className="rounded-2xl border p-3">
                    <div className="text-sm font-medium">{reminder.message}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {reminder.room_name} • {formatTimestamp(reminder.fire_at)}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed p-3 text-sm text-muted-foreground">
                  No pending reminders yet.
                </div>
              )}
            </div>

            <div className="space-y-3">
              <div className="text-sm font-semibold">Focus tasks</div>
              {loading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <LoaderCircle className="size-4 animate-spin" />
                  Loading tasks
                </div>
              ) : dashboard?.today.focus_tasks.length ? (
                dashboard.today.focus_tasks.map((task) => (
                  <div key={task.id} className="rounded-2xl border p-3">
                    <div className="text-sm font-medium">{task.title}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {task.room_name} • {task.due_date ? formatTimestamp(task.due_date) : "No due date"}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed p-3 text-sm text-muted-foreground">
                  No open tasks across your rooms.
                </div>
              )}
            </div>

            <div className="space-y-3">
              <div className="text-sm font-semibold">Recent approval requests</div>
              {loading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <LoaderCircle className="size-4 animate-spin" />
                  Loading approvals
                </div>
              ) : dashboard?.today.approval_requests.length ? (
                dashboard.today.approval_requests.map((item) => (
                  <div key={item.id} className="rounded-2xl border p-3">
                    <div className="text-sm font-medium">{item.tool_name}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {item.room_name} • {formatTimestamp(item.created_at)}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Expires {formatTimestamp(item.expires_at)}
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground">{item.tool_args_preview}</div>
                    <div className="mt-2 text-xs text-muted-foreground">{item.reason}</div>
                    <div className="mt-3 flex gap-2">
                      <LoadingButton
                        size="sm"
                        loading={actioningApprovalId === item.id}
                        onClick={() => handleApprovalAction(item.id, "approve")}
                      >
                        Approve
                      </LoadingButton>
                      <LoadingButton
                        size="sm"
                        variant="destructive"
                        loading={actioningApprovalId === item.id}
                        onClick={() => handleApprovalAction(item.id, "deny")}
                      >
                        Deny
                      </LoadingButton>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed p-3 text-sm text-muted-foreground">
                  No pending confirmation requests.
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Guardian status</CardTitle>
            <CardDescription>
              Live status for routing and scheduled jobs.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Badge variant={dashboard?.summary.task_guardian_enabled ? "default" : "outline"}>
                Task Guardian {dashboard?.summary.task_guardian_enabled ? "on" : "off"}
              </Badge>
              <Badge variant={dashboard?.summary.token_guardian_mode === "live" ? "default" : "secondary"}>
                Token Guardian {dashboard?.summary.token_guardian_mode}
              </Badge>
            </div>
            <div className="rounded-2xl border p-4 text-sm text-muted-foreground">
              {dashboard?.summary.guardian_jobs_enabled ?? 0} enabled jobs out of {dashboard?.summary.guardian_jobs ?? 0}.
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Estimated savings 24h</div>
                <div className="mt-1 text-lg font-semibold">
                  {formatMoney(dashboard?.today.token_guardian.estimated_savings_24h)}
                </div>
              </div>
              <div className="rounded-2xl border p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Live routes 24h</div>
                <div className="mt-1 text-lg font-semibold">
                  {dashboard?.today.token_guardian.live_routes_24h ?? 0}
                </div>
              </div>
            </div>
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <LoaderCircle className="size-4 animate-spin" />
                Loading Guardian jobs
              </div>
            ) : dashboard?.today.guardian_jobs.length ? (
              dashboard.today.guardian_jobs.map((job) => (
                <div key={job.id} className="rounded-2xl border p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-medium">{job.name}</div>
                    <Badge variant={job.enabled ? "default" : "outline"}>
                      {job.enabled ? "Enabled" : "Paused"}
                    </Badge>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {job.room_name} • {job.tool_name}
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    Next run: {formatTimestamp(job.next_run_at)}
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed p-3 text-sm text-muted-foreground">
                No Task Guardian jobs configured yet.
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      {currentUser?.is_superuser && <SpineWorkStateSection />}

      <section className="grid gap-4 xl:grid-cols-[1fr_1fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Inbox</CardTitle>
            <CardDescription>
              Gmail or IMAP summary from the configured inbox integration.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Badge variant={dashboard?.today.inbox.configured ? "default" : "outline"}>
                {dashboard?.today.inbox.configured ? dashboard?.today.inbox.source : "Not configured"}
              </Badge>
            </div>
            <div className="rounded-2xl border p-4 text-sm leading-6 text-muted-foreground whitespace-pre-wrap">
              {loading ? "Loading inbox summary..." : dashboard?.today.inbox.summary_text}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Meeting artifacts</CardTitle>
            <CardDescription>
              Recent notes, decisions, and action-item captures across your rooms.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <LoaderCircle className="size-4 animate-spin" />
                Loading meetings
              </div>
            ) : dashboard?.today.meetings.length ? (
              dashboard.today.meetings.map((meeting) => (
                <div key={meeting.id} className="rounded-2xl border p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-medium capitalize">{meeting.type.split("_").join(" ")}</div>
                    <Badge variant="outline">{meeting.room_name}</Badge>
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    {formatTimestamp(meeting.created_at)}
                  </div>
                  <div className="mt-2 text-sm leading-6 text-muted-foreground">{meeting.excerpt}</div>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed p-3 text-sm text-muted-foreground">
                No meeting artifacts captured yet.
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Token Guardian routing</CardTitle>
            <CardDescription>
              Current mode, request volume, and top model mix.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Mode</div>
                <div className="mt-1 text-lg font-semibold capitalize">
                  {dashboard?.today.token_guardian.mode ?? "off"}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {dashboard?.today.token_guardian.live_ready ? "Live-ready" : "Missing configured route targets"}
                </div>
              </div>
              <div className="rounded-2xl border p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Requests</div>
                <div className="mt-1 text-lg font-semibold">
                  {dashboard?.today.token_guardian.requests ?? 0}
                </div>
              </div>
              <div className="rounded-2xl border p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Tracked tokens</div>
                <div className="mt-1 text-lg font-semibold">
                  {dashboard?.today.token_guardian.total_tokens ?? 0}
                </div>
              </div>
              <div className="rounded-2xl border p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Tracked cost</div>
                <div className="mt-1 text-lg font-semibold">
                  {formatMoney(dashboard?.today.token_guardian.total_cost)}
                </div>
              </div>
            </div>
            <div className="rounded-2xl border p-4">
              <div className="text-sm font-semibold">Live routing envelope</div>
              <div className="mt-2 text-sm text-muted-foreground">
                Allowed: {dashboard?.today.token_guardian.allowed_live_models.join(", ") || "None"}
              </div>
              <div className="mt-1 text-sm text-muted-foreground">
                Configured: {dashboard?.today.token_guardian.configured_models.join(", ") || "None"}
              </div>
            </div>
            <div className="rounded-2xl border p-4">
              <div className="text-sm font-semibold">Last route</div>
              {loading ? (
                <div className="mt-2 text-sm text-muted-foreground">Loading last route...</div>
              ) : dashboard?.today.token_guardian.last_route ? (
                <div className="mt-3 space-y-2 text-sm">
                  <div className="text-muted-foreground">
                    {dashboard.today.token_guardian.last_route.current_model} →{" "}
                    <span className="font-medium text-foreground">
                      {dashboard.today.token_guardian.last_route.applied_model}
                    </span>
                  </div>
                  <div className="text-muted-foreground capitalize">
                    {dashboard.today.token_guardian.last_route.classification || "general"} •{" "}
                    {formatTimestamp(dashboard.today.token_guardian.last_route.created_at)}
                  </div>
                  <div className="text-muted-foreground">
                    Requested {dashboard.today.token_guardian.last_route.selected_model || "unknown"}
                  </div>
                  {dashboard.today.token_guardian.last_route.fallback_reason ? (
                    <div className="rounded-xl bg-muted px-3 py-2 text-muted-foreground">
                      {dashboard.today.token_guardian.last_route.fallback_reason}
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="mt-2 text-sm text-muted-foreground">
                  No Token Guardian route has been recorded yet.
                </div>
              )}
            </div>
            <div className="rounded-2xl border p-4">
              <div className="text-sm font-semibold">Top routed models</div>
              <div className="mt-3 space-y-2">
                {loading ? (
                  <div className="text-sm text-muted-foreground">Loading routing data...</div>
                ) : dashboard?.today.token_guardian.top_models.length ? (
                  dashboard.today.token_guardian.top_models.map((item) => (
                    <div key={item.model} className="flex items-center justify-between gap-3 text-sm">
                      <span className="truncate text-muted-foreground">{item.model}</span>
                      <span className="font-medium">{item.tokens}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-sm text-muted-foreground">No Token Guardian usage tracked yet.</div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        {moduleCards.map((card) => (
          <Card key={card.title} className="overflow-hidden">
            <CardHeader className="gap-3">
              <div className="flex size-10 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <card.icon className="size-5" />
              </div>
              <div>
                <CardTitle className="text-base">{card.title}</CardTitle>
                <CardDescription className="mt-2 leading-6">{card.description}</CardDescription>
              </div>
            </CardHeader>
          </Card>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Next build slices</CardTitle>
            <CardDescription>
              The shell is intentionally static first. Data widgets should land in this order.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            {[
              "Daily brief personalization and waiting-for logic.",
              "Interactive approvals queue with approve/deny from the dashboard.",
              "Task Guardian write-actions with confirmation routing.",
              "Token Guardian live-routing rollout controls and fallback policy.",
              "Richer inbox triage cards and draft workflows.",
              "Channel health for web, Telegram, Discord, and WhatsApp.",
            ].map((item, index) => (
              <div key={item} className="flex gap-3 rounded-2xl border p-4">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
                  {index + 1}
                </div>
                <p className="text-sm leading-6 text-muted-foreground">{item}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="border-chart-2/25">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-medium text-chart-2">
              <Waves className="size-4" />
              Launch stance
            </div>
            <CardTitle className="text-lg">Personal assistant + office worker</CardTitle>
            <CardDescription>
              Keep the security story, but lead with usefulness: what matters today, what needs approval,
              what Sparkbot can finish for you, and what it recommends next.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
            <p>
              The dashboard should become the desktop default for self-hosted installs, with DM remaining
              the deep work surface.
            </p>
            <p>
              Once the data widgets land, this page can replace the current template dashboard entirely
              and serve as the central command center for local PC, homelab, and server deployments.
            </p>
          </CardContent>
        </Card>
      </section>

      {error ? (
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="text-lg">Dashboard data unavailable</CardTitle>
            <CardDescription>
              The shell rendered, but the aggregate API did not respond cleanly.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">{error}</CardContent>
        </Card>
      ) : null}
    </div>
  )
}
