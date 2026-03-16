import { Link, createFileRoute, redirect } from "@tanstack/react-router"
import { ArrowLeft, Database, LoaderCircle, RefreshCw } from "lucide-react"
import { useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { UsersService } from "@/client"
import {
  type SpineApproval,
  type SpineEvent,
  type SpineHandoff,
  type SpineProducer,
  type SpineProject,
  type SpineQueueName,
  type SpineTask,
  type SpineTaskLineage,
  type SpineTMOverview,
  type SpineProjectWorkloadEntry,
  fetchSpineProjectWorkload,
  fetchSpineProducers,
  fetchSpineProjects,
  fetchSpineQueue,
  fetchSpineRecentEvents,
  fetchSpineTMOverview,
  fetchSpineTaskDetail,
} from "@/lib/spine"

export const Route = createFileRoute("/_layout/spine")({
  component: SpineOps,
  beforeLoad: async () => {
    const user = await UsersService.readUserMe()
    if (!user.is_superuser) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({
    meta: [{ title: "Spine Ops - Sparkbot" }],
  }),
})

// ─── Inspector target union ───────────────────────────────────────────────────

type InspectorTarget =
  | { kind: "task"; task: SpineTask }
  | { kind: "project"; project: SpineProject; workload?: SpineProjectWorkloadEntry }
  | { kind: "event"; event: SpineEvent }
  | null

// ─── Queue descriptions ───────────────────────────────────────────────────────

const QUEUE_INFO: Record<SpineQueueName, string> = {
  "open": "Active work — open, triaged, queued, or in progress",
  "blocked": "Waiting for a dependency or external action",
  "approval-waiting": "Cannot proceed until the operator approves",
  "stale": "Not progressed within expected threshold for its priority",
  "orphaned": "No project linkage — may be fragmented or missing context",
  "missing-source": "Cannot trace origin — no source_kind or source_ref",
  "missing-project": "Not attached to any project — needs assignment",
  "resurfaced": "Previously dormant; reopened by the memory subsystem",
  "executive-directives": "Executive-tagged directives requiring owner assignment",
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatRelativeTime(value: string | null | undefined): string {
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

function formatFullTimestamp(value: string | null | undefined): string {
  if (!value) return "—"
  try {
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(value))
  } catch {
    return value
  }
}

function formatEventType(et: string): string {
  return et.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

// ─── Error box ────────────────────────────────────────────────────────────────

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-2 text-sm text-destructive">
      {message}
    </div>
  )
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function SpineStatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return null
  const s = status.toLowerCase()
  const variant =
    s === "blocked"
      ? "destructive"
      : s === "done" || s === "archived" || s === "candidate"
        ? "secondary"
        : s === "approval_waiting"
          ? "outline"
          : s === "stale"
            ? "outline"
            : "default"

  const extra =
    s === "approval_waiting"
      ? " text-yellow-600 dark:text-yellow-400 border-yellow-400"
      : s === "stale"
        ? " text-muted-foreground"
        : ""

  return (
    <Badge variant={variant} className={`text-xs${extra}`}>
      {status}
    </Badge>
  )
}

function SpineStatTile({
  label,
  count,
  highlight = false,
}: {
  label: string
  count: number
  highlight?: boolean
}) {
  return (
    <div
      className={`rounded-xl border px-3 py-2 text-center ${highlight && count > 0 ? "border-destructive/40 bg-destructive/5" : ""}`}
    >
      <div className={`text-lg font-semibold ${highlight && count > 0 ? "text-destructive" : ""}`}>{count}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  )
}

function SpineTaskRow({ task, onSelect }: { task: SpineTask; onSelect?: (t: SpineTask) => void }) {
  return (
    <div
      className={`flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-sm ${onSelect ? "cursor-pointer hover:bg-muted/50 transition-colors" : ""}`}
      onClick={() => onSelect?.(task)}
    >
      <span className="min-w-0 flex-1 truncate font-medium">{task.title || task.task_id}</span>
      <SpineStatusBadge status={task.status} />
      {task.priority && (
        <Badge variant="outline" className="text-xs text-muted-foreground">
          {task.priority}
        </Badge>
      )}
      {task.source_kind && (
        <span className="text-xs text-muted-foreground">{task.source_kind}</span>
      )}
      {task.room_id && (
        <span className="max-w-[120px] truncate text-xs text-muted-foreground">{task.room_id}</span>
      )}
      <span className="text-xs text-muted-foreground">{formatRelativeTime(task.updated_at)}</span>
    </div>
  )
}

function SpineQueueTable({
  queueName,
  refreshKey,
  onSelect,
}: {
  queueName: SpineQueueName
  refreshKey: number
  onSelect: (t: SpineTask) => void
}) {
  const [result, setResult] = useState<{ tasks: SpineTask[]; count: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [fetched, setFetched] = useState(false)

  useEffect(() => {
    if (fetched) return
    setFetched(true)
    setLoading(true)
    fetchSpineQueue(queueName, 50)
      .then(setResult)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false))
  }, [queueName, fetched, refreshKey])

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading {queueName} queue…
      </div>
    )
  }
  if (error) return <ErrorBox message={error} />
  if (!result) return null

  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">{result.count} tasks</div>
      {result.tasks.length === 0 ? (
        <div className="rounded-xl border border-dashed px-4 py-3 text-sm text-muted-foreground">No tasks in this queue.</div>
      ) : (
        result.tasks.map((t) => <SpineTaskRow key={t.task_id} task={t} onSelect={onSelect} />)
      )}
    </div>
  )
}

function SpineProjectTable({
  refreshKey,
  workloadData,
  onSelect,
}: {
  refreshKey: number
  workloadData: SpineProjectWorkloadEntry[]
  onSelect: (p: SpineProject, workload?: SpineProjectWorkloadEntry) => void
}) {
  const [result, setResult] = useState<{ projects: SpineProject[]; count: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    setLoading(true)
    fetchSpineProjects(100)
      .then(setResult)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false))
  }, [refreshKey])

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading projects…
      </div>
    )
  }
  if (error) return <ErrorBox message={error} />
  if (!result) return null

  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">{result.count} projects</div>
      {result.projects.length === 0 ? (
        <div className="rounded-xl border border-dashed px-4 py-3 text-sm text-muted-foreground">No projects registered in the Spine.</div>
      ) : (
        result.projects.map((p) => {
          const wl = workloadData.find((w) => w.project_id === p.project_id)
          return (
            <div
              key={p.project_id}
              className="flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-sm cursor-pointer hover:bg-muted/50 transition-colors"
              onClick={() => onSelect(p, wl)}
            >
              <span className="min-w-0 flex-1 truncate font-medium">{p.display_name || p.slug}</span>
              <SpineStatusBadge status={p.status} />
              {p.owner_kind && <span className="text-xs text-muted-foreground">{p.owner_kind}</span>}
              {p.room_id && <span className="max-w-[120px] truncate text-xs text-muted-foreground">{p.room_id}</span>}
              {p.tags.map((tag) => (
                <Badge key={tag} variant="outline" className="text-xs">
                  {tag}
                </Badge>
              ))}
              <span className="text-xs text-muted-foreground">{formatRelativeTime(p.updated_at)}</span>
            </div>
          )
        })
      )}
    </div>
  )
}

function SpineEventsPanel({
  limit,
  refreshKey,
  onSelect,
}: {
  limit: number
  refreshKey: number
  onSelect: (e: SpineEvent) => void
}) {
  const [result, setResult] = useState<{ events: SpineEvent[]; count: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    setLoading(true)
    fetchSpineRecentEvents(limit)
      .then(setResult)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false))
  }, [limit, refreshKey])

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading events…
      </div>
    )
  }
  if (error) return <ErrorBox message={error} />
  if (!result) return null

  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">{result.count} events</div>
      {result.events.length === 0 ? (
        <div className="rounded-xl border border-dashed px-4 py-3 text-sm text-muted-foreground">No events recorded yet.</div>
      ) : (
        result.events.map((e) => (
          <div
            key={e.event_id}
            className="flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-sm cursor-pointer hover:bg-muted/50 transition-colors"
            onClick={() => onSelect(e)}
          >
            <span className="font-medium">{formatEventType(e.event_type)}</span>
            <Badge variant="outline" className="text-xs">
              {e.subsystem}
            </Badge>
            {e.task_id && <span className="max-w-[140px] truncate text-xs text-muted-foreground">{e.task_id}</span>}
            {e.project_id && (
              <span className="max-w-[140px] truncate text-xs text-muted-foreground">{e.project_id}</span>
            )}
            <span className="ml-auto text-xs text-muted-foreground">{formatRelativeTime(e.occurred_at)}</span>
          </div>
        ))
      )}
    </div>
  )
}

function SpineProducersPanel({ refreshKey }: { refreshKey: number }) {
  const [result, setResult] = useState<{ producers: SpineProducer[]; count: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    setLoading(true)
    fetchSpineProducers()
      .then(setResult)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false))
  }, [refreshKey])

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading producers…
      </div>
    )
  }
  if (error) return <ErrorBox message={error} />
  if (!result) return null

  return (
    <div className="space-y-3">
      <div className="text-xs text-muted-foreground">{result.count} registered producers</div>
      {result.producers.length === 0 ? (
        <div className="rounded-xl border border-dashed px-4 py-3 text-sm text-muted-foreground">No producers registered.</div>
      ) : (
        result.producers.map((p) => (
          <div key={p.subsystem} className="rounded-xl border px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{p.subsystem}</span>
              <span className="text-sm text-muted-foreground">{p.description}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {p.event_types.map((et) => (
                <Badge key={et} variant="secondary" className="text-xs">
                  {et}
                </Badge>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  )
}

// ─── Project workload summary table ───────────────────────────────────────────

function SpineWorkloadTable({ refreshKey }: { refreshKey: number }) {
  const [result, setResult] = useState<{ projects: SpineProjectWorkloadEntry[]; count: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    setLoading(true)
    fetchSpineProjectWorkload()
      .then(setResult)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false))
  }, [refreshKey])

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" /> Loading workload…
      </div>
    )
  }
  if (error) return <ErrorBox message={error} />
  if (!result || result.projects.length === 0) {
    return (
      <div className="rounded-xl border border-dashed px-4 py-3 text-sm text-muted-foreground">No project workload data.</div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th className="pb-2 pr-4 text-left font-medium">Project</th>
            <th className="pb-2 pr-4 text-left font-medium">Status</th>
            <th className="pb-2 pr-4 text-right font-medium">Total</th>
            <th className="pb-2 pr-4 text-right font-medium">Open</th>
            <th className="pb-2 pr-4 text-right font-medium">Blocked</th>
            <th className="pb-2 text-right font-medium">Stale</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {result.projects.map((p) => (
            <tr key={p.project_id} className="text-sm">
              <td className="py-2 pr-4 font-medium">{p.display_name}</td>
              <td className="py-2 pr-4">
                <SpineStatusBadge status={p.status} />
              </td>
              <td className="py-2 pr-4 text-right">{p.total_tasks}</td>
              <td className="py-2 pr-4 text-right">{p.open_tasks}</td>
              <td className="py-2 pr-4 text-right text-destructive">{p.blocked_tasks}</td>
              <td className="py-2 text-right text-muted-foreground">{p.stale_tasks ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Inspector sub-components ─────────────────────────────────────────────────

function InspectorField({ label, value }: { label: string; value: React.ReactNode }) {
  if (!value && value !== 0) return null
  return (
    <div className="flex gap-3 text-sm">
      <span className="w-32 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 break-all">{value}</span>
    </div>
  )
}

function TaskInspector({
  task,
  onTaskClick,
}: {
  task: SpineTask
  onTaskClick: (t: SpineTask) => void
}) {
  const [lineage, setLineage] = useState<SpineTaskLineage | null>(null)
  const [lineageLoading, setLineageLoading] = useState(true)
  const [lineageError, setLineageError] = useState("")

  useEffect(() => {
    setLineageLoading(true)
    setLineageError("")
    fetchSpineTaskDetail(task.task_id)
      .then(setLineage)
      .catch((e: unknown) => setLineageError(e instanceof Error ? e.message : "Failed to load lineage"))
      .finally(() => setLineageLoading(false))
  }, [task.task_id])

  // Information scent callout
  const callout: string | null =
    task.status === "blocked"
      ? "Blocked — waiting for dependency or external action"
      : task.approval_state === "required" || task.approval_state === "requested"
        ? "Awaiting approval before proceeding"
        : !task.source_kind || !task.source_ref
          ? "⚠ Missing source traceability"
          : !task.project_id
            ? "⚠ No project linkage"
            : task.tags.includes("executive")
              ? "Executive directive"
              : task.tags.includes("resurfaced")
                ? "Resurfaced from memory"
                : null

  return (
    <div className="space-y-4">
      <SheetHeader>
        <SheetTitle className="flex flex-wrap items-center gap-2 text-base">
          <span className="min-w-0 flex-1">{task.title || task.task_id}</span>
          <SpineStatusBadge status={task.status} />
          {task.type && (
            <Badge variant="secondary" className="text-xs">
              {task.type}
            </Badge>
          )}
        </SheetTitle>
      </SheetHeader>

      {callout && (
        <div className="rounded-xl border border-yellow-400/40 bg-yellow-50/50 px-3 py-2 text-sm text-yellow-700 dark:bg-yellow-950/20 dark:text-yellow-400">
          {callout}
        </div>
      )}

      <div className="space-y-1.5">
        <InspectorField label="Priority" value={task.priority} />
        <InspectorField label="Owner" value={task.owner_kind ? `${task.owner_kind}${task.owner_id ? ` / ${task.owner_id}` : ""}` : null} />
        <InspectorField label="Room" value={task.room_id} />
        <InspectorField label="Project" value={task.project_id} />
        <InspectorField label="Source" value={task.source_kind ? `${task.source_kind}${task.source_ref ? ` / ${task.source_ref}` : ""}` : null} />
        <InspectorField label="Confidence" value={task.confidence !== null ? `${Math.round((task.confidence ?? 0) * 100)}%` : null} />
        <InspectorField label="Approval state" value={task.approval_state} />
        <InspectorField label="Created by" value={task.created_by_subsystem} />
        <InspectorField label="Updated by" value={task.updated_by_subsystem} />
      </div>

      {task.summary && (
        <div className="rounded-xl border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
          {task.summary}
        </div>
      )}

      {task.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {task.tags.map((tag) => (
            <Badge key={tag} variant="outline" className="text-xs">
              {tag}
            </Badge>
          ))}
        </div>
      )}

      <div className="space-y-1 text-xs text-muted-foreground">
        <div>Created: {formatFullTimestamp(task.created_at)}</div>
        <div>Updated: {formatFullTimestamp(task.updated_at)}</div>
        {task.last_progress_at && <div>Last progress: {formatFullTimestamp(task.last_progress_at)}</div>}
        {task.closed_at && <div>Closed: {formatFullTimestamp(task.closed_at)}</div>}
      </div>

      <div className="border-t pt-4">
        <div className="mb-2 text-xs font-semibold text-muted-foreground">Lineage</div>
        {lineageLoading ? (
          <div className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin" /> Loading lineage…
          </div>
        ) : lineageError ? (
          <ErrorBox message={lineageError} />
        ) : lineage ? (
          <div className="space-y-3">
            {lineage.parent && (
              <div>
                <div className="mb-1 text-xs text-muted-foreground">Parent</div>
                <div
                  className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm cursor-pointer hover:bg-muted/50"
                  onClick={() => onTaskClick(lineage.parent!)}
                >
                  <span className="min-w-0 flex-1 truncate">{lineage.parent.title || lineage.parent.task_id}</span>
                  <SpineStatusBadge status={lineage.parent.status} />
                </div>
              </div>
            )}

            {lineage.children.length > 0 && (
              <div>
                <div className="mb-1 text-xs text-muted-foreground">{lineage.children.length} children</div>
                <div className="space-y-1">
                  {lineage.children.slice(0, 5).map((c) => (
                    <div
                      key={c.task_id}
                      className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm cursor-pointer hover:bg-muted/50"
                      onClick={() => onTaskClick(c)}
                    >
                      <span className="min-w-0 flex-1 truncate">{c.title || c.task_id}</span>
                      <SpineStatusBadge status={c.status} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {lineage.dependencies.length > 0 && (
              <div>
                <div className="mb-1 text-xs text-muted-foreground">{lineage.dependencies.length} dependencies</div>
                <div className="space-y-1">
                  {lineage.dependencies.map((d) => (
                    <div
                      key={d.task_id}
                      className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm cursor-pointer hover:bg-muted/50"
                      onClick={() => onTaskClick(d)}
                    >
                      <span className="min-w-0 flex-1 truncate">{d.title || d.task_id}</span>
                      <SpineStatusBadge status={d.status} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {lineage.approvals.length > 0 && (
              <div>
                <div className="mb-1 text-xs text-muted-foreground">Approvals</div>
                <div className="space-y-1">
                  {lineage.approvals.map((a: SpineApproval) => (
                    <div key={a.id} className="rounded-lg border px-3 py-2 text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{a.state}</span>
                      {a.approval_method && <span> · {a.approval_method}</span>}
                      {a.expires_at && <span> · expires {formatRelativeTime(a.expires_at)}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {lineage.handoffs.length > 0 && (
              <div>
                <div className="mb-1 text-xs text-muted-foreground">Handoffs</div>
                <div className="space-y-1">
                  {lineage.handoffs.map((h: SpineHandoff) => (
                    <div key={h.id} className="rounded-lg border px-3 py-2 text-xs">
                      <div className="text-sm">{h.summary}</div>
                      <div className="mt-1 text-muted-foreground">
                        {h.room_id} · {formatRelativeTime(h.created_at)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {!lineage.parent && lineage.children.length === 0 && lineage.dependencies.length === 0 && lineage.approvals.length === 0 && lineage.handoffs.length === 0 && (
              <div className="text-sm text-muted-foreground">No lineage data.</div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function ProjectInspector({
  project,
  workload,
}: {
  project: SpineProject
  workload?: SpineProjectWorkloadEntry
}) {
  return (
    <div className="space-y-4">
      <SheetHeader>
        <SheetTitle className="flex flex-wrap items-center gap-2 text-base">
          <span className="min-w-0 flex-1">{project.display_name || project.slug}</span>
          <SpineStatusBadge status={project.status} />
        </SheetTitle>
      </SheetHeader>

      <div className="space-y-1.5">
        <InspectorField label="Slug" value={project.slug} />
        <InspectorField label="Owner" value={project.owner_kind ? `${project.owner_kind}${project.owner_id ? ` / ${project.owner_id}` : ""}` : null} />
        <InspectorField label="Room" value={project.room_id} />
        <InspectorField label="Source" value={project.source_kind ? `${project.source_kind}${project.source_ref ? ` / ${project.source_ref}` : ""}` : null} />
        <InspectorField label="Created by" value={project.created_by_subsystem} />
        <InspectorField label="Updated by" value={project.updated_by_subsystem} />
      </div>

      {project.summary && (
        <div className="rounded-xl border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
          {project.summary}
        </div>
      )}

      {project.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {project.tags.map((tag) => (
            <Badge key={tag} variant="outline" className="text-xs">
              {tag}
            </Badge>
          ))}
        </div>
      )}

      {workload && (
        <div className="rounded-xl border px-3 py-2">
          <div className="mb-2 text-xs font-semibold text-muted-foreground">Task workload</div>
          <div className="grid grid-cols-2 gap-1 text-sm">
            <div className="text-muted-foreground">Total</div><div>{workload.total_tasks}</div>
            <div className="text-muted-foreground">Open</div><div>{workload.open_tasks}</div>
            <div className="text-muted-foreground">Blocked</div><div className="text-destructive">{workload.blocked_tasks}</div>
            {workload.stale_tasks !== undefined && <><div className="text-muted-foreground">Stale</div><div>{workload.stale_tasks}</div></>}
            {workload.approval_waiting_tasks !== undefined && <><div className="text-muted-foreground">Approval</div><div>{workload.approval_waiting_tasks}</div></>}
          </div>
        </div>
      )}

      <div className="space-y-1 text-xs text-muted-foreground">
        {project.created_at && <div>Created: {formatFullTimestamp(project.created_at)}</div>}
        <div>Updated: {formatFullTimestamp(project.updated_at)}</div>
      </div>

      <div className="rounded-xl border border-dashed px-3 py-2 text-xs text-muted-foreground">
        Project mutations route through project_executive adapter — not yet wired to UI.
      </div>
    </div>
  )
}

function EventInspector({
  event,
  onTaskClick,
  onProjectClick,
}: {
  event: SpineEvent
  onTaskClick: (taskId: string) => void
  onProjectClick: (projectId: string) => void
}) {
  const [showRaw, setShowRaw] = useState(false)
  const payload = event.payload ?? {}
  const payloadKeys = Object.keys(payload)
  const highlightKeys = new Set(["action", "reason", "status", "model", "error", "message", "task_id"])

  return (
    <div className="space-y-4">
      <SheetHeader>
        <SheetTitle className="flex flex-wrap items-center gap-2 text-base">
          <span className="min-w-0 flex-1">{formatEventType(event.event_type)}</span>
          <Badge variant="secondary" className="text-xs">
            {event.subsystem}
          </Badge>
        </SheetTitle>
      </SheetHeader>

      <div className="space-y-1.5">
        <InspectorField label="Actor" value={event.actor_kind ? `${event.actor_kind}${event.actor_id ? ` / ${event.actor_id}` : ""}` : null} />
        <InspectorField label="Source" value={event.source_kind ? `${event.source_kind}${event.source_ref ? ` / ${event.source_ref}` : ""}` : null} />
        <InspectorField label="Occurred" value={formatFullTimestamp(event.occurred_at)} />
        <InspectorField
          label="Correlation"
          value={
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{event.correlation_id}</span>
          }
        />
      </div>

      {event.task_id && (
        <div
          className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm cursor-pointer hover:bg-muted/50"
          onClick={() => onTaskClick(event.task_id!)}
        >
          <span className="text-muted-foreground text-xs">Task</span>
          <span className="min-w-0 flex-1 truncate font-mono text-xs">{event.task_id}</span>
        </div>
      )}

      {event.project_id && (
        <div
          className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm cursor-pointer hover:bg-muted/50"
          onClick={() => onProjectClick(event.project_id!)}
        >
          <span className="text-muted-foreground text-xs">Project</span>
          <span className="min-w-0 flex-1 truncate font-mono text-xs">{event.project_id}</span>
        </div>
      )}

      <div>
        <div className="mb-2 text-xs font-semibold text-muted-foreground">Payload</div>
        {payloadKeys.length === 0 ? (
          <div className="text-sm text-muted-foreground">No payload</div>
        ) : (
          <div className="space-y-1">
            {payloadKeys.map((key) => {
              const raw = payload[key]
              const str = typeof raw === "string" ? raw : JSON.stringify(raw)
              const truncated = str.length > 200 ? str.slice(0, 200) + "…" : str
              return (
                <div key={key} className="flex gap-2 text-sm">
                  <span className={`w-28 shrink-0 font-mono text-xs ${highlightKeys.has(key) ? "text-primary font-semibold" : "text-muted-foreground"}`}>
                    {key}
                  </span>
                  <span className="min-w-0 flex-1 break-all text-xs">{truncated}</span>
                </div>
              )
            })}
            <button
              className="mt-2 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              onClick={() => setShowRaw((v) => !v)}
            >
              {showRaw ? "Hide" : "Show"} raw JSON
            </button>
            {showRaw && (
              <pre className="mt-2 overflow-x-auto rounded-lg border bg-muted/40 p-3 text-xs">
                {JSON.stringify(payload, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Inspector Sheet ──────────────────────────────────────────────────────────

function SpineInspectorSheet({
  inspector,
  onClose,
  onTaskClick,
  onTaskIdClick,
  onProjectIdClick,
}: {
  inspector: InspectorTarget
  onClose: () => void
  onTaskClick: (t: SpineTask) => void
  onTaskIdClick: (taskId: string) => void
  onProjectIdClick: (projectId: string) => void
}) {
  return (
    <Sheet open={inspector !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        {inspector?.kind === "task" && (
          <TaskInspector task={inspector.task} onTaskClick={onTaskClick} />
        )}
        {inspector?.kind === "project" && (
          <ProjectInspector project={inspector.project} workload={inspector.workload} />
        )}
        {inspector?.kind === "event" && (
          <EventInspector
            event={inspector.event}
            onTaskClick={onTaskIdClick}
            onProjectClick={onProjectIdClick}
          />
        )}
      </SheetContent>
    </Sheet>
  )
}

// ─── Queue inner-tab names ────────────────────────────────────────────────────

const QUEUE_TABS: Array<{ label: string; value: SpineQueueName }> = [
  { label: "Open", value: "open" },
  { label: "Blocked", value: "blocked" },
  { label: "Approval", value: "approval-waiting" },
  { label: "Stale", value: "stale" },
  { label: "Orphaned", value: "orphaned" },
  { label: "Resurfaced", value: "resurfaced" },
  { label: "Executive", value: "executive-directives" },
  { label: "Missing Source", value: "missing-source" },
  { label: "Missing Project", value: "missing-project" },
]

// ─── Main component ────────────────────────────────────────────────────────────

function SpineOps() {
  const [overview, setOverview] = useState<SpineTMOverview | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(true)
  const [overviewError, setOverviewError] = useState("")
  const [activeTab, setActiveTab] = useState<"overview" | "queues" | "projects" | "events" | "producers">("overview")
  const [activeQueue, setActiveQueue] = useState<SpineQueueName>("open")
  const [eventsLimit, setEventsLimit] = useState(25)
  const [refreshKey, setRefreshKey] = useState(0)
  const [inspector, setInspector] = useState<InspectorTarget>(null)
  const [workloadData, setWorkloadData] = useState<SpineProjectWorkloadEntry[]>([])

  useEffect(() => {
    setOverviewLoading(true)
    setOverviewError("")
    fetchSpineTMOverview(10)
      .then(setOverview)
      .catch((e: unknown) => setOverviewError(e instanceof Error ? e.message : "Failed to load overview"))
      .finally(() => setOverviewLoading(false))
    // Also fetch workload data for the project inspector
    fetchSpineProjectWorkload()
      .then((r) => setWorkloadData(r.projects))
      .catch(() => {/* non-critical */})
  }, [refreshKey])

  const stats: Array<{ label: string; key: keyof SpineTMOverview; highlight?: boolean }> = [
    { label: "Open", key: "open_queue" },
    { label: "Blocked", key: "blocked_queue", highlight: true },
    { label: "Approval", key: "approval_waiting_queue", highlight: true },
    { label: "Stale", key: "stale_queue" },
    { label: "Orphaned", key: "orphan_queue" },
    { label: "Resurfaced", key: "recently_resurfaced_queue" },
    { label: "Ready", key: "assignment_ready_queue" },
  ]

  function handleTaskClick(task: SpineTask) {
    setInspector({ kind: "task", task })
  }

  function handleProjectClick(project: SpineProject, workload?: SpineProjectWorkloadEntry) {
    setInspector({ kind: "project", project, workload })
  }

  function handleEventClick(event: SpineEvent) {
    setInspector({ kind: "event", event })
  }

  // When clicking a task ID from an event inspector (we only have the ID, not the full task object)
  // We open a minimal task "shell" — the lineage fetch in TaskInspector will populate the rest
  function handleTaskIdClick(taskId: string) {
    // Find task in overview data if available, otherwise create a minimal shell
    const allTasks = [
      ...(overview?.open_queue ?? []),
      ...(overview?.blocked_queue ?? []),
      ...(overview?.orphan_queue ?? []),
      ...(overview?.approval_waiting_queue ?? []),
      ...(overview?.stale_queue ?? []),
      ...(overview?.recently_resurfaced_queue ?? []),
      ...(overview?.assignment_ready_queue ?? []),
    ]
    const found = allTasks.find((t) => t.task_id === taskId)
    if (found) {
      setInspector({ kind: "task", task: found })
    }
    // If not found in cache, we can't open (no task object). Event payload shows the ID at minimum.
  }

  return (
    <div className="space-y-6">
      <SpineInspectorSheet
        inspector={inspector}
        onClose={() => setInspector(null)}
        onTaskClick={handleTaskClick}
        onTaskIdClick={handleTaskIdClick}
        onProjectIdClick={(_id) => {
          // Project lookup by ID alone not yet supported — project data requires a list fetch
        }}
      />

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Database className="size-5 text-primary" />
            <h1 className="text-2xl font-semibold tracking-tight">Guardian Spine Ops</h1>
            <Badge variant="outline" className="rounded-full">
              Operator
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Guardian Spine · Canonical work-state substrate. Task Master executes over it. Mirrors and legacy tables are
            one-way downstream reflections.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/">
            <Button variant="ghost" size="sm" className="gap-1.5">
              <ArrowLeft className="size-3.5" /> Dashboard
            </Button>
          </Link>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => setRefreshKey((k) => k + 1)}
            disabled={overviewLoading}
          >
            <RefreshCw className={`size-3.5 ${overviewLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Summary bar */}
      {overviewError ? (
        <ErrorBox message={overviewError} />
      ) : (
        <div className="grid grid-cols-4 gap-2 sm:grid-cols-7">
          {stats.map(({ label, key, highlight }) => {
            const arr = overview?.[key] as SpineTask[] | undefined
            return (
              <SpineStatTile key={label} label={label} count={arr?.length ?? 0} highlight={highlight} />
            )
          })}
        </div>
      )}

      {/* Note */}
      <div className="rounded-xl border border-dashed px-4 py-2 text-xs text-muted-foreground">
        Project-level execution routing is not yet unified — project actions are read-only in this release. Actions via
        project_executive adapter are not yet wired to the UI.
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 border-b pb-0">
        {(["overview", "queues", "projects", "events", "producers"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`rounded-t px-4 py-2 text-sm font-medium capitalize transition-colors ${
              activeTab === tab
                ? "border-b-2 border-primary text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Project workload</CardTitle>
              <CardDescription>Task distribution across active projects.</CardDescription>
            </CardHeader>
            <CardContent>
              <SpineWorkloadTable refreshKey={refreshKey} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent events</CardTitle>
              <CardDescription>Last 10 spine events.</CardDescription>
            </CardHeader>
            <CardContent>
              <SpineEventsPanel limit={10} refreshKey={refreshKey} onSelect={handleEventClick} />
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "queues" && (
        <div className="space-y-4">
          {/* Inner queue tabs */}
          <div className="flex flex-wrap gap-1">
            {QUEUE_TABS.map(({ label, value }) => (
              <button
                key={value}
                onClick={() => setActiveQueue(value)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeQueue === value
                    ? "border-primary bg-primary/10 text-primary"
                    : "text-muted-foreground hover:border-primary/40 hover:text-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {/* Queue description */}
          <div className="text-xs text-muted-foreground">{QUEUE_INFO[activeQueue]}</div>
          <SpineQueueTable
            key={`${activeQueue}-${refreshKey}`}
            queueName={activeQueue}
            refreshKey={refreshKey}
            onSelect={handleTaskClick}
          />
        </div>
      )}

      {activeTab === "projects" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Projects</CardTitle>
            <CardDescription>All projects in the canonical spine registry.</CardDescription>
          </CardHeader>
          <CardContent>
            <SpineProjectTable
              refreshKey={refreshKey}
              workloadData={workloadData}
              onSelect={handleProjectClick}
            />
          </CardContent>
        </Card>
      )}

      {activeTab === "events" && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">Event log</CardTitle>
                <CardDescription>Recent spine events across all producers.</CardDescription>
              </div>
              <div className="flex gap-1">
                {[25, 50, 100].map((n) => (
                  <button
                    key={n}
                    onClick={() => setEventsLimit(n)}
                    className={`rounded border px-2 py-1 text-xs transition-colors ${
                      eventsLimit === n
                        ? "border-primary bg-primary/10 text-primary"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <SpineEventsPanel key={eventsLimit} limit={eventsLimit} refreshKey={refreshKey} onSelect={handleEventClick} />
          </CardContent>
        </Card>
      )}

      {activeTab === "producers" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Producer registry</CardTitle>
            <CardDescription>All registered spine event producers and their event types.</CardDescription>
          </CardHeader>
          <CardContent>
            <SpineProducersPanel refreshKey={refreshKey} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
