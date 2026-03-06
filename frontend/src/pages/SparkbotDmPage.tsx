// Sparkbot DM Page — streaming, slash commands, syntax highlighting, search, meeting mode

import { useState, useEffect, useCallback, useRef } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { Check, Copy, Loader2, Paperclip, RefreshCw, Search, Send, Settings2, X } from "lucide-react"
import ReactMarkdown from "react-markdown"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export const Route = createFileRoute("/dm")({
  component: SparkbotDmPage,
})

// ─── Confirm modal ────────────────────────────────────────────────────────────

interface PendingConfirm {
  confirmId: string
  tool: string
  input: Record<string, unknown>
}

function describeAction(tool: string, input: Record<string, unknown>): string {
  switch (tool) {
    case "gmail_send":
      return `Send Gmail message to ${input.to ?? "?"} — subject: ${input.subject ?? "(none)"}`
    case "email_send":
      return `Send email to ${input.to ?? "?"} — subject: ${input.subject ?? "(none)"}`
    case "drive_create_folder":
      return `Create Drive folder ${input.name ?? "?"}`
    case "slack_send_message":
      return `Post to Slack #${input.channel ?? "?"}: ${String(input.text ?? "").slice(0, 80)}`
    case "github_create_issue":
      return `Create GitHub issue: ${input.title ?? "?"}`
    case "notion_create_page":
      return `Create Notion page: ${input.title ?? "?"}`
    case "confluence_create_page":
      return `Create Confluence page: ${input.title ?? "?"}`
    case "calendar_create_event":
      return `Create calendar event: ${input.title ?? input.summary ?? "?"}`
    case "server_manage_service":
      return `Run service action: ${input.action ?? "?"} ${input.service ?? "?"}`
    case "guardian_schedule_task":
      return `Schedule Task Guardian job: ${input.name ?? "?"} via ${input.tool_name ?? "?"}`
    default:
      return `Execute ${tool}`
  }
}

function ConfirmModal({ pending, onConfirm, onCancel }: {
  pending: PendingConfirm
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-sm rounded-xl border bg-popover p-6 shadow-xl">
        <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
          <span>⚠️</span>
          <span>Confirm action</span>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">{describeAction(pending.tool, pending.input)}</p>
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-md border px-4 py-1.5 text-sm hover:bg-muted">
            Cancel
          </button>
          <button onClick={onConfirm} className="rounded-md bg-primary px-4 py-1.5 text-sm text-primary-foreground hover:opacity-90">
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface Message {
  id: string
  content: string
  created_at: string
  sender_type?: string
  sender_username?: string
  isStreaming?: boolean
  isSystem?: boolean
  toolActivity?: string   // e.g. "🔍 Searching: climate change 2026"
  agent?: string          // named agent that responded, e.g. "researcher"
}

interface RoomInfo {
  id: string
  name: string
  execution_allowed: boolean
}

interface PolicyEntry {
  id: string
  created_at: string
  tool_result: {
    action?: string
    reason?: string
    resource?: string
  } | string
}

interface GuardianTaskRecord {
  id: string
  name: string
  tool_name: string
  schedule: string
  enabled: boolean
  next_run_at?: string | null
  last_status?: string | null
  last_message?: string | null
}

interface GuardianRunRecord {
  run_id: string
  task_id: string
  status: string
  message: string
  created_at: string
}

interface Agent {
  name: string
  emoji: string
  description: string
}

// Built-in agents — mirrors backend agents.py (shown before API loads)
const BUILTIN_AGENTS: Agent[] = [
  { name: "researcher", emoji: "🔍", description: "Research specialist — finds accurate info, searches the web" },
  { name: "coder",      emoji: "💻", description: "Software engineer — clean, working code with explanations" },
  { name: "writer",     emoji: "✍️", description: "Professional writer — drafts, edits, structures content" },
  { name: "analyst",    emoji: "📊", description: "Data analyst — structured reasoning and actionable insights" },
]

// ─── Slash commands ───────────────────────────────────────────────────────────

interface SlashCommand {
  name: string
  description: string
}

const COMMANDS: SlashCommand[] = [
  { name: "/help",    description: "Show available commands" },
  { name: "/clear",   description: "Clear visible chat history" },
  { name: "/new",     description: "Start a fresh conversation" },
  { name: "/export",  description: "Download conversation as Markdown" },
  { name: "/search",  description: "Search messages — e.g. /search invoice" },
  { name: "/meeting", description: "Meeting mode — /meeting start | stop | notes" },
  { name: "/model",   description: "Switch AI model — e.g. /model gpt-4o" },
  { name: "/memory",  description: "View or clear what Sparkbot remembers about you" },
  { name: "/tasks",   description: "List open tasks — /tasks | /tasks done | /tasks all" },
  { name: "/remind",  description: "List pending reminders for this room" },
  { name: "/agents",  description: "List available named agents (@researcher, @coder, etc.)" },
  { name: "/audit",   description: "Show recent bot tool actions" },
]

function systemMsg(content: string): Message {
  return { id: `sys-${Date.now()}-${Math.random()}`, content, created_at: new Date().toISOString(), sender_type: "SYSTEM", isSystem: true }
}

// ─── Code block ───────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })}
      className="absolute right-2 top-2 z-10 rounded p-1 text-zinc-400 opacity-0 transition-opacity group-hover/code:opacity-100 hover:text-zinc-100"
      title="Copy code"
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </button>
  )
}

function CodeBlock({ language, children }: { language?: string; children: string }) {
  return (
    <div className="group/code relative my-2">
      <CopyButton text={children} />
      <SyntaxHighlighter language={language || "text"} style={oneDark} customStyle={{ borderRadius: "0.375rem", fontSize: "0.8rem", margin: 0 }} PreTag="div">
        {children}
      </SyntaxHighlighter>
    </div>
  )
}

const TOOL_ICONS: Record<string, string> = {
  web_search:            "🔍",
  get_datetime:          "🕐",
  calculate:             "🧮",
  create_task:           "📋",
  list_tasks:            "📋",
  complete_task:         "✅",
  github_list_prs:       "🐙",
  github_get_pr:         "🐙",
  github_create_issue:   "🐙",
  github_get_ci_status:  "🔬",
  gmail_fetch_inbox:     "📬",
  gmail_search:          "📬",
  gmail_get_message:     "📬",
  gmail_send:            "📤",
  drive_search:          "📁",
  drive_get_file:        "📁",
  drive_create_folder:   "📁",
  email_fetch_inbox:     "📧",
  email_search:          "📧",
  email_send:            "📤",
  server_read_command:   "🖥️",
  server_manage_service: "🛠️",
  ssh_read_command:      "🔐",
  set_reminder:          "⏰",
  list_reminders:        "⏰",
  cancel_reminder:       "⏰",
  guardian_schedule_task: "🛡️",
  guardian_list_tasks:    "🛡️",
  guardian_list_runs:     "🛡️",
  guardian_run_task:      "🛡️",
  guardian_pause_task:    "🛡️",
  calendar_list_events:    "📅",
  calendar_create_event:   "📅",
  slack_send_message:      "💬",
  slack_list_channels:     "💬",
  slack_get_channel_history: "💬",
  notion_search:           "📝",
  notion_get_page:         "📝",
  notion_create_page:      "📝",
  confluence_search:       "🏔️",
  confluence_get_page:     "🏔️",
  confluence_create_page:  "🏔️",
}

function ToolChip({ activity }: { activity: string }) {
  return (
    <div className="mb-2 flex items-center gap-1.5 rounded-md border border-dashed border-zinc-600 bg-zinc-800/50 px-2 py-1 text-xs text-zinc-400 animate-pulse">
      <span>{activity}</span>
    </div>
  )
}

const AGENT_INFO: Record<string, { emoji: string; label: string }> = {
  researcher: { emoji: "🔍", label: "researcher" },
  coder:      { emoji: "💻", label: "coder" },
  writer:     { emoji: "✍️", label: "writer" },
  analyst:    { emoji: "📊", label: "analyst" },
}

function BotMessage({ content, isStreaming, toolActivity, agent }: { content: string; isStreaming?: boolean; toolActivity?: string; agent?: string }) {
  const agentInfo = agent ? AGENT_INFO[agent] : null
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none break-words text-sm">
      {agentInfo && (
        <div className="mb-1.5 flex items-center gap-1 text-[10px] font-semibold text-muted-foreground">
          <span>{agentInfo.emoji}</span>
          <span className="uppercase tracking-wide">{agentInfo.label}</span>
        </div>
      )}
      {toolActivity && <ToolChip activity={toolActivity} />}
      <ReactMarkdown
        components={{
          code({ className, children }) {
            const text = String(children).replace(/\n$/, "")
            const match = /language-(\w+)/.exec(className || "")
            if (!match && !text.includes("\n")) {
              return <code className="rounded bg-zinc-800 px-1 py-0.5 font-mono text-xs text-zinc-200">{text}</code>
            }
            return <CodeBlock language={match?.[1]}>{text}</CodeBlock>
          },
          p({ children }) { return <p className="mb-2 last:mb-0">{children}</p> },
          ul({ children }) { return <ul className="mb-2 ml-4 list-disc">{children}</ul> },
          ol({ children }) { return <ol className="mb-2 ml-4 list-decimal">{children}</ol> },
          h1({ children }) { return <h1 className="mb-2 text-base font-bold">{children}</h1> },
          h2({ children }) { return <h2 className="mb-2 text-sm font-bold">{children}</h2> },
          h3({ children }) { return <h3 className="mb-1 text-sm font-semibold">{children}</h3> },
          blockquote({ children }) { return <blockquote className="mb-2 border-l-2 border-zinc-400 pl-3 italic text-muted-foreground">{children}</blockquote> },
          img({ src, alt }) { return <img src={src} alt={alt || ""} className="my-2 max-w-full rounded-lg max-h-80 object-contain" /> },
          a({ href, children }) { return <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline">{children}</a> },
        }}
      >
        {content}
      </ReactMarkdown>
      {isStreaming && <span className="inline-block h-4 w-2 animate-pulse bg-current opacity-70" />}
    </div>
  )
}

// ─── Command autocomplete ─────────────────────────────────────────────────────

function CommandPicker({ query, onSelect }: { query: string; onSelect: (cmd: string) => void }) {
  const matches = COMMANDS.filter(c => c.name.startsWith(query))
  if (!matches.length) return null
  return (
    <div className="absolute bottom-full left-0 mb-1 w-80 rounded-lg border bg-popover shadow-lg overflow-hidden z-20">
      {matches.map(cmd => (
        <button key={cmd.name} onMouseDown={e => { e.preventDefault(); onSelect(cmd.name + " ") }}
          className="flex w-full items-start gap-3 px-3 py-2 text-left hover:bg-muted">
          <span className="font-mono text-sm font-semibold text-primary shrink-0">{cmd.name}</span>
          <span className="text-xs text-muted-foreground mt-0.5">{cmd.description}</span>
        </button>
      ))}
    </div>
  )
}

// ─── Agent picker ─────────────────────────────────────────────────────────────

function AgentPicker({ query, agents, onSelect }: { query: string; agents: Agent[]; onSelect: (name: string) => void }) {
  const q = query.slice(1).toLowerCase() // strip leading @
  const matches = agents.filter(a => a.name.startsWith(q))
  if (!matches.length) return null
  return (
    <div className="absolute bottom-full left-0 mb-1 w-80 rounded-lg border bg-popover shadow-lg overflow-hidden z-20">
      {matches.map(agent => (
        <button key={agent.name} onMouseDown={e => { e.preventDefault(); onSelect(agent.name) }}
          className="flex w-full items-start gap-3 px-3 py-2 text-left hover:bg-muted">
          <span className="text-base shrink-0">{agent.emoji}</span>
          <div>
            <span className="font-mono text-sm font-semibold text-primary">@{agent.name}</span>
            <p className="text-xs text-muted-foreground mt-0.5">{agent.description}</p>
          </div>
        </button>
      ))}
    </div>
  )
}

// ─── Search panel ─────────────────────────────────────────────────────────────

function highlight(text: string, query: string): React.ReactNode {
  if (!query) return text
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return text
  const start = Math.max(0, idx - 40)
  const excerpt = (start > 0 ? "…" : "") + text.slice(start, idx + query.length + 80)
  const qi = excerpt.toLowerCase().indexOf(query.toLowerCase())
  if (qi === -1) return excerpt
  return <>{excerpt.slice(0, qi)}<mark className="bg-yellow-200 dark:bg-yellow-700 rounded px-0.5">{excerpt.slice(qi, qi + query.length)}</mark>{excerpt.slice(qi + query.length)}</>
}

interface SearchPanelProps {
  roomId: string
  onClose: () => void
}

function SearchPanel({ roomId, onClose }: SearchPanelProps) {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<Message[]>([])
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const doSearch = useCallback(async (q: string) => {
    const trimmed = q.trim()
    if (trimmed.length < 2) { setResults([]); setSearched(false); return }
    setSearching(true)
    try {
      const res = await fetch(`/api/v1/chat/messages/${roomId}/search?q=${encodeURIComponent(trimmed)}&limit=30`, {
        credentials: "include",
      })
      if (res.ok) {
        const data = await res.json()
        setResults(data.messages ?? [])
      }
    } catch { /* ignore */ } finally {
      setSearching(false)
      setSearched(true)
    }
  }, [roomId])

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => doSearch(query), 350)
    return () => clearTimeout(t)
  }, [query, doSearch])

  return (
    <div className="absolute inset-0 z-30 flex flex-col bg-background">
      {/* Search header */}
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <Search className="size-4 text-muted-foreground shrink-0" />
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === "Escape" && onClose()}
          placeholder="Search messages…"
          className="flex-1 bg-transparent text-sm outline-none"
        />
        {searching && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
        <button onClick={onClose} className="rounded p-1 hover:bg-muted">
          <X className="size-4" />
        </button>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-auto px-4 py-2 space-y-1">
        {!searched && query.length < 2 && (
          <p className="text-center text-sm text-muted-foreground py-8">Type at least 2 characters to search</p>
        )}
        {searched && results.length === 0 && (
          <p className="text-center text-sm text-muted-foreground py-8">No messages found for <strong>"{query}"</strong></p>
        )}
        {results.map(msg => {
          const isBot = String(msg.sender_type ?? "").toUpperCase() === "BOT"
          return (
            <div key={msg.id} className="rounded-lg border bg-muted/30 px-3 py-2 text-sm">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-semibold ${isBot ? "text-primary" : "text-foreground"}`}>
                  {isBot ? "Sparkbot" : (msg.sender_username ?? "You")}
                </span>
                <span className="text-xs text-muted-foreground">
                  {new Date(msg.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </span>
              </div>
              <p className="text-muted-foreground leading-snug">{highlight(msg.content, query)}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface SparkbotSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  room: RoomInfo | null
  loading: boolean
  savingExecution: boolean
  policyEntries: PolicyEntry[]
  guardianTasks: GuardianTaskRecord[]
  guardianRuns: GuardianRunRecord[]
  taskName: string
  taskToolName: string
  taskSchedule: string
  taskArgs: string
  taskSaving: boolean
  error: string
  onRefresh: () => void
  onToggleExecution: (enabled: boolean) => void
  onTaskNameChange: (value: string) => void
  onTaskToolChange: (value: string) => void
  onTaskScheduleChange: (value: string) => void
  onTaskArgsChange: (value: string) => void
  onCreateTask: () => void
  onToggleTask: (taskId: string, enabled: boolean) => void
  onRunTask: (taskId: string) => void
}

const TASK_TOOL_OPTIONS = [
  "gmail_fetch_inbox",
  "gmail_search",
  "github_list_prs",
  "github_get_ci_status",
  "calendar_list_events",
  "drive_search",
  "web_search",
  "server_read_command",
  "ssh_read_command",
  "list_tasks",
  "list_reminders",
]

function SparkbotSettingsDialog({
  open,
  onOpenChange,
  room,
  loading,
  savingExecution,
  policyEntries,
  guardianTasks,
  guardianRuns,
  taskName,
  taskToolName,
  taskSchedule,
  taskArgs,
  taskSaving,
  error,
  onRefresh,
  onToggleExecution,
  onTaskNameChange,
  onTaskToolChange,
  onTaskScheduleChange,
  onTaskArgsChange,
  onCreateTask,
  onToggleTask,
  onRunTask,
}: SparkbotSettingsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Sparkbot Controls</DialogTitle>
          <DialogDescription>
            Room execution gate, approval visibility, and Task Guardian schedules.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          <section className="rounded-xl border p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">Execution Gate</h2>
                <p className="text-xs text-muted-foreground">
                  Server and SSH tools fail closed unless this room is explicitly allowed to execute them.
                </p>
              </div>
              <button
                onClick={onRefresh}
                className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
                type="button"
              >
                <span className="inline-flex items-center gap-1">
                  <RefreshCw className="size-3.5" />
                  Refresh
                </span>
              </button>
            </div>
            <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/40 px-3 py-3">
              <div>
                <div className="text-sm font-medium">Allow machine operations in this room</div>
                <div className="text-xs text-muted-foreground">
                  Required for `server_read_command`, `ssh_read_command`, and `server_manage_service`.
                </div>
              </div>
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={Boolean(room?.execution_allowed)}
                disabled={savingExecution || !room}
                onChange={(e) => onToggleExecution(e.target.checked)}
              />
            </label>
          </section>

          <section className="rounded-xl border p-4">
            <div className="mb-3">
              <h2 className="text-sm font-semibold">Task Guardian</h2>
              <p className="text-xs text-muted-foreground">
                Schedule approved read-only routines and post results back into this room.
              </p>
            </div>

            <div className="grid gap-3 rounded-lg bg-muted/40 p-3 md:grid-cols-2">
              <input
                value={taskName}
                onChange={(e) => onTaskNameChange(e.target.value)}
                placeholder="Task name"
                className="rounded-md border bg-background px-3 py-2 text-sm outline-none"
              />
              <select
                value={taskToolName}
                onChange={(e) => onTaskToolChange(e.target.value)}
                className="rounded-md border bg-background px-3 py-2 text-sm outline-none"
              >
                {TASK_TOOL_OPTIONS.map((tool) => (
                  <option key={tool} value={tool}>{tool}</option>
                ))}
              </select>
              <input
                value={taskSchedule}
                onChange={(e) => onTaskScheduleChange(e.target.value)}
                placeholder="every:3600 or at:2026-03-07T14:00:00Z"
                className="rounded-md border bg-background px-3 py-2 text-sm outline-none md:col-span-2"
              />
              <textarea
                value={taskArgs}
                onChange={(e) => onTaskArgsChange(e.target.value)}
                placeholder='{"max_emails": 5, "unread_only": true}'
                rows={4}
                className="rounded-md border bg-background px-3 py-2 text-sm font-mono outline-none md:col-span-2"
              />
              <div className="md:col-span-2 flex justify-end">
                <button
                  type="button"
                  onClick={onCreateTask}
                  disabled={taskSaving}
                  className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
                >
                  {taskSaving ? "Saving..." : "Create scheduled job"}
                </button>
              </div>
            </div>

            <div className="mt-4 space-y-2">
              {guardianTasks.length === 0 ? (
                <p className="text-sm text-muted-foreground">No scheduled jobs yet.</p>
              ) : guardianTasks.map((task) => (
                <div key={task.id} className="rounded-lg border px-3 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium">{task.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {task.tool_name} · {task.schedule}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => onRunTask(task.id)}
                        className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
                      >
                        Run now
                      </button>
                      <button
                        type="button"
                        onClick={() => onToggleTask(task.id, !task.enabled)}
                        className="rounded-md border px-2 py-1 text-xs hover:bg-muted"
                      >
                        {task.enabled ? "Pause" : "Resume"}
                      </button>
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    {task.next_run_at ? `Next run: ${new Date(task.next_run_at).toLocaleString()}` : "No next run scheduled"}
                    {task.last_status ? ` · Last status: ${task.last_status}` : ""}
                    {task.last_message ? ` · ${task.last_message}` : ""}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Recent scheduled runs</h3>
              <div className="space-y-2">
                {guardianRuns.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No runs recorded yet.</p>
                ) : guardianRuns.map((run) => (
                  <div key={run.run_id} className="rounded-lg border px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{run.status.toUpperCase()}</span>
                      <span className="text-xs text-muted-foreground">{new Date(run.created_at).toLocaleString()}</span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{run.message}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="rounded-xl border p-4">
            <h2 className="mb-3 text-sm font-semibold">Recent Approval / Policy Decisions</h2>
            <div className="space-y-2">
              {policyEntries.length === 0 ? (
                <p className="text-sm text-muted-foreground">No policy decisions logged for this room yet.</p>
              ) : policyEntries.map((entry) => {
                const decision = typeof entry.tool_result === "string" ? { action: "", reason: entry.tool_result, resource: "" } : entry.tool_result
                return (
                  <div key={entry.id} className="rounded-lg border px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium uppercase">{decision.action || "decision"}</span>
                      <span className="text-xs text-muted-foreground">{new Date(entry.created_at).toLocaleString()}</span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {decision.resource ? `${decision.resource}: ` : ""}{decision.reason || "No reason recorded."}
                    </p>
                  </div>
                )
              })}
            </div>
          </section>

          {(loading || error) && (
            <div className="rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground">
              {loading ? "Loading controls..." : error}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ─── Meeting mode state ───────────────────────────────────────────────────────

interface MeetingState {
  active: boolean
  startedAt: Date | null
  notes: string[]
  decisions: string[]
  actions: string[]
}

const emptyMeeting = (): MeetingState => ({ active: false, startedAt: null, notes: [], decisions: [], actions: [] })

// ─── Main page ────────────────────────────────────────────────────────────────

function SparkbotDmPage() {
  const [roomId, setRoomId] = useState<string | null>(null)
  const [roomInfo, setRoomInfo] = useState<RoomInfo | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [inputValue, setInputValue] = useState("")
  const [showCommands, setShowCommands] = useState(false)
  const [showAgentPicker, setShowAgentPicker] = useState(false)
  const [agents, setAgents] = useState<Agent[]>(BUILTIN_AGENTS)
  const [showSearch, setShowSearch] = useState(false)
  const [meeting, setMeeting] = useState<MeetingState>(emptyMeeting())
  const [uploading, setUploading] = useState(false)
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [settingsError, setSettingsError] = useState("")
  const [savingExecution, setSavingExecution] = useState(false)
  const [policyEntries, setPolicyEntries] = useState<PolicyEntry[]>([])
  const [guardianTasks, setGuardianTasks] = useState<GuardianTaskRecord[]>([])
  const [guardianRuns, setGuardianRuns] = useState<GuardianRunRecord[]>([])
  const [taskName, setTaskName] = useState("")
  const [taskToolName, setTaskToolName] = useState("gmail_fetch_inbox")
  const [taskSchedule, setTaskSchedule] = useState("every:3600")
  const [taskArgs, setTaskArgs] = useState('{"max_emails": 5, "unread_only": true}')
  const [taskSaving, setTaskSaving] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages])
  useEffect(() => { setShowCommands(inputValue.startsWith("/") && !inputValue.includes(" ")) }, [inputValue])
  useEffect(() => { setShowAgentPicker(inputValue.startsWith("@") && !inputValue.includes(" ")) }, [inputValue])

  useEffect(() => {
    async function init() {
      if (!sessionStorage.getItem("chat_auth") && !localStorage.getItem("access_token")) {
        window.location.href = "/login"; return
      }
      try {
        const res = await fetch("/api/v1/chat/users/bootstrap", { method: "POST", credentials: "include" })
        if (!res.ok) { window.location.href = "/login"; return }
        const boot = await res.json()
        setRoomId(boot.room_id)
        const roomRes = await fetch(`/api/v1/chat/rooms/${boot.room_id}`, { credentials: "include" })
        if (roomRes.ok) {
          const room = await roomRes.json()
          setRoomInfo(room)
        }
        const msgsRes = await fetch(`/api/v1/chat/rooms/${boot.room_id}/messages`, { credentials: "include" })
        if (msgsRes.ok) {
          const d = await msgsRes.json()
          setMessages(d.messages ?? d.items ?? (Array.isArray(d) ? d : []))
        }
        // Load agent list (falls back to BUILTIN_AGENTS if request fails)
        try {
          const agentsRes = await fetch("/api/v1/chat/agents", { credentials: "include" })
          if (agentsRes.ok) { const ag = await agentsRes.json(); setAgents(ag.agents ?? BUILTIN_AGENTS) }
        } catch { /* keep built-ins */ }
      } catch (e) { console.error(e) } finally { setLoading(false) }
    }
    init()
  }, [])

  const refreshControls = useCallback(async () => {
    if (!roomId) return
    setSettingsLoading(true)
    setSettingsError("")
    try {
      const [roomRes, policyRes, tasksRes, runsRes] = await Promise.all([
        fetch(`/api/v1/chat/rooms/${roomId}`, { credentials: "include" }),
        fetch(`/api/v1/chat/audit?limit=10&room_id=${roomId}&tool=policy_decision`, { credentials: "include" }),
        fetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks?limit=20`, { credentials: "include" }),
        fetch(`/api/v1/chat/rooms/${roomId}/guardian/runs?limit=10`, { credentials: "include" }),
      ])

      if (roomRes.ok) {
        setRoomInfo(await roomRes.json())
      }
      if (policyRes.ok) {
        const data = await policyRes.json()
        setPolicyEntries(data.items ?? [])
      }
      if (tasksRes.ok) {
        const data = await tasksRes.json()
        setGuardianTasks(data.items ?? [])
      }
      if (runsRes.ok) {
        const data = await runsRes.json()
        setGuardianRuns(data.items ?? [])
      }
    } catch {
      setSettingsError("Could not load Sparkbot controls.")
    } finally {
      setSettingsLoading(false)
    }
  }, [roomId])

  useEffect(() => {
    if (settingsOpen) {
      refreshControls()
    }
  }, [settingsOpen, refreshControls])

  const toggleExecutionGate = useCallback(async (enabled: boolean) => {
    if (!roomId) return
    setSavingExecution(true)
    setSettingsError("")
    try {
      const res = await fetch(`/api/v1/chat/rooms/${roomId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ execution_allowed: enabled }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Could not update execution gate." }))
        setSettingsError(data.detail ?? "Could not update execution gate.")
      } else {
        const data = await res.json()
        setRoomInfo(data)
      }
    } catch {
      setSettingsError("Could not update execution gate.")
    } finally {
      setSavingExecution(false)
    }
  }, [roomId])

  const createGuardianTask = useCallback(async () => {
    if (!roomId) return
    setTaskSaving(true)
    setSettingsError("")
    try {
      const parsedArgs = taskArgs.trim() ? JSON.parse(taskArgs) : {}
      const res = await fetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          name: taskName.trim(),
          tool_name: taskToolName,
          schedule: taskSchedule.trim(),
          tool_args: parsedArgs,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Could not create Task Guardian job." }))
        setSettingsError(data.detail ?? "Could not create Task Guardian job.")
      } else {
        const created = await res.json()
        setTaskName("")
        setMessages(prev => [...prev, systemMsg(`Scheduled Task Guardian job **${created.name}**.`)])
        await refreshControls()
      }
    } catch {
      setSettingsError("Task arguments must be valid JSON.")
    } finally {
      setTaskSaving(false)
    }
  }, [roomId, taskArgs, taskName, taskSchedule, taskToolName, refreshControls])

  const setGuardianTaskState = useCallback(async (taskId: string, enabled: boolean) => {
    if (!roomId) return
    setSettingsError("")
    try {
      const res = await fetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ enabled }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Could not update Task Guardian job." }))
        setSettingsError(data.detail ?? "Could not update Task Guardian job.")
      } else {
        setMessages(prev => [...prev, systemMsg(`Task Guardian job ${enabled ? "**resumed**" : "**paused**"}.`)])
        await refreshControls()
      }
    } catch {
      setSettingsError("Could not update Task Guardian job.")
    }
  }, [roomId, refreshControls])

  const runGuardianTask = useCallback(async (taskId: string) => {
    if (!roomId) return
    setSettingsError("")
    try {
      const res = await fetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks/${taskId}/run`, {
        method: "POST",
        credentials: "include",
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: "Could not run Task Guardian job." }))
        setSettingsError(data.detail ?? "Could not run Task Guardian job.")
      } else {
        const data = await res.json()
        setMessages(prev => [...prev, systemMsg(`Task Guardian run finished with **${String(data.status ?? "unknown").toUpperCase()}**.\n\n${String(data.output ?? "").slice(0, 400)}`)])
        await refreshControls()
      }
    } catch {
      setSettingsError("Could not run Task Guardian job.")
    }
  }, [roomId, refreshControls])

  // ── Meeting helpers ──────────────────────────────────────────────────────────

  const formatMeetingNotes = useCallback((m: MeetingState): string => {
    const dur = m.startedAt ? Math.round((Date.now() - m.startedAt.getTime()) / 60000) : 0
    return [
      `## Meeting Notes — ${new Date().toLocaleDateString()}`,
      `Duration: ~${dur} min`,
      m.notes.length    ? `\n### Notes\n${m.notes.map(n => `- ${n}`).join("\n")}`       : "",
      m.decisions.length? `\n### Decisions\n${m.decisions.map(d => `- ${d}`).join("\n")}`: "",
      m.actions.length  ? `\n### Action Items\n${m.actions.map(a => `- [ ] ${a}`).join("\n")}`: "",
    ].filter(Boolean).join("\n")
  }, [])

  // ── Slash command handlers ───────────────────────────────────────────────────

  const handleCommand = useCallback((raw: string): boolean => {
    const parts = raw.trim().split(/\s+/)
    const cmd = parts[0]
    const args = parts.slice(1).join(" ")

    if (cmd === "/help") {
      const text = COMMANDS.map(c => `**${c.name}** — ${c.description}`).join("\n")
      setMessages(prev => [...prev, systemMsg(text)])
      return true
    }

    if (cmd === "/audit") {
      if (!roomId) return true
      fetch(`/api/v1/chat/audit?limit=10&room_id=${roomId}`, { credentials: "include" })
        .then(r => r.json())
        .then(data => {
          const items: any[] = data.items ?? []
          if (!items.length) {
            setMessages(prev => [...prev, systemMsg("No audit log entries yet. Tool actions will appear here.")])
            return
          }
          const lines = ["**Recent bot actions:**\n"]
          items.forEach((e: any) => {
            const ts = new Date(e.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
            const agent = e.agent_name ? ` [@${e.agent_name}]` : ""
            const input = typeof e.tool_input === "object"
              ? Object.entries(e.tool_input).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")
              : String(e.tool_input)
            lines.push(`\`${ts}\`${agent} **${e.tool_name}**(${input.slice(0, 80)})`)
            lines.push(`  ↳ ${e.tool_result.replace(/\n/g, " ").slice(0, 100)}`)
          })
          setMessages(prev => [...prev, systemMsg(lines.join("\n"))])
        })
        .catch(() => setMessages(prev => [...prev, systemMsg("Failed to load audit log.")]))
      return true
    }

    if (cmd === "/agents") {
      const lines = ["**Available agents** — mention with @name:\n"]
      agents.forEach(a => lines.push(`${a.emoji} **@${a.name}** — ${a.description}`))
      lines.push("\nExample: `@researcher what's the latest on quantum computing?`")
      setMessages(prev => [...prev, systemMsg(lines.join("\n"))])
      return true
    }

    if (cmd === "/clear") {
      setMessages([systemMsg("Chat cleared locally. History still on server.")])
      return true
    }

    if (cmd === "/new") {
      setMessages([systemMsg("Fresh start. Previous history still on server.")])
      return true
    }

    if (cmd === "/export") {
      const lines = messages.filter(m => !m.isSystem).map(m => {
        const who = String(m.sender_type ?? "").toUpperCase() === "BOT" ? "**Sparkbot**" : "**You**"
        return `### ${who} — ${new Date(m.created_at).toLocaleString()}\n\n${m.content}`
      }).join("\n\n---\n\n")
      const blob = new Blob([`# Sparkbot Conversation\n\n${lines}`], { type: "text/markdown" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a"); a.href = url; a.download = `sparkbot-${new Date().toISOString().slice(0,10)}.md`; a.click()
      URL.revokeObjectURL(url)
      setMessages(prev => [...prev, systemMsg("Exported as Markdown.")])
      return true
    }

    if (cmd === "/search") {
      if (!args) {
        setMessages(prev => [...prev, systemMsg("Usage: **/search** &lt;query&gt; — or click the 🔍 icon in the header.")])
        return true
      }
      setShowSearch(true)
      return true
    }

    if (cmd === "/model") {
      if (!args) {
        // List available models
        fetch("/api/v1/chat/models", { credentials: "include" })
          .then(r => r.json())
          .then(data => {
            const lines = data.models.map((m: { id: string; description: string; active: boolean }) =>
              `${m.active ? "✅" : "⬜"} \`${m.id}\` — ${m.description}`
            ).join("\n")
            setMessages(prev => [...prev, systemMsg(`**Available models** (✅ = active):\n\n${lines}\n\nUse **/model &lt;id&gt;** to switch.`)])
          })
          .catch(() => setMessages(prev => [...prev, systemMsg("⚠️ Could not fetch model list.")]))
        return true
      }
      // Set model
      fetch("/api/v1/chat/model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ model: args.trim() }),
      })
        .then(async r => {
          if (!r.ok) {
            const e = await r.json().catch(() => ({ detail: "Unknown error" }))
            setMessages(prev => [...prev, systemMsg(`⚠️ ${e.detail ?? "Could not set model."}`)])
          } else {
            const d = await r.json()
            setMessages(prev => [...prev, systemMsg(`Model switched to **${d.model}** — ${d.description}`)])
          }
        })
        .catch(() => setMessages(prev => [...prev, systemMsg("⚠️ Could not switch model.")]))
      return true
    }

    if (cmd === "/memory") {
      if (!args || args === "list") {
        fetch("/api/v1/chat/memory/", { credentials: "include" })
          .then(r => r.json())
          .then(data => {
            if (!data.memories?.length) {
              setMessages(prev => [...prev, systemMsg("No memories stored yet. Sparkbot will remember things as you chat.")])
              return
            }
            const lines = data.memories.map((m: { id: string; fact: string; created_at: string }) =>
              `- ${m.fact} *(id: \`${m.id.slice(0, 8)}\`)*`
            ).join("\n")
            setMessages(prev => [...prev, systemMsg(`**Sparkbot remembers (${data.count}):**\n\n${lines}\n\nTo forget one: tell Sparkbot "forget that I ..." or use **/memory clear** to wipe all.`)])
          })
          .catch(() => setMessages(prev => [...prev, systemMsg("⚠️ Could not fetch memories.")]))
        return true
      }
      if (args === "clear") {
        fetch("/api/v1/chat/memory/", { method: "DELETE", credentials: "include" })
          .then(r => r.json())
          .then(d => setMessages(prev => [...prev, systemMsg(`Cleared ${d.cleared} memories.`)]))
          .catch(() => setMessages(prev => [...prev, systemMsg("⚠️ Could not clear memories.")]))
        return true
      }
      setMessages(prev => [...prev, systemMsg("**Memory commands:**\n- **/memory** — list what Sparkbot knows about you\n- **/memory clear** — wipe all memories")])
      return true
    }

    if (cmd === "/tasks") {
      if (!roomId) { setMessages(prev => [...prev, systemMsg("⚠️ Room not loaded yet.")]); return true }
      const filter = args === "done" ? "done" : args === "all" ? "all" : "open"
      fetch(`/api/v1/chat/rooms/${roomId}/tasks?filter=${filter}`, { credentials: "include" })
        .then(r => r.json())
        .then(data => {
          if (!data.tasks?.length) {
            setMessages(prev => [...prev, systemMsg(`No ${filter} tasks in this room.\n\nTo add one, just tell Sparkbot: *"Add a task to review the report"*`)])
            return
          }
          const lines = data.tasks.map((t: { id: string; title: string; status: string; assigned_to: string | null; due_date: string | null }) => {
            const icon = t.status === "done" ? "✅" : "⬜"
            const assignee = t.assigned_to ? ` *(${t.assigned_to.slice(0, 8)})*` : ""
            const due = t.due_date ? ` — due ${t.due_date.slice(0, 10)}` : ""
            return `${icon} \`${t.id.slice(0, 8)}\` ${t.title}${assignee}${due}`
          }).join("\n")
          setMessages(prev => [...prev, systemMsg(`**Tasks (${filter}) — ${data.count}:**\n\n${lines}\n\nTell Sparkbot to *"mark [task] as done"* or *"add a task to ..."*`)])
        })
        .catch(() => setMessages(prev => [...prev, systemMsg("⚠️ Could not fetch tasks.")]))
      return true
    }

    if (cmd === "/remind") {
      if (!roomId) { setMessages(prev => [...prev, systemMsg("⚠️ Room not loaded yet.")]); return true }
      fetch(`/api/v1/chat/rooms/${roomId}/reminders?status=pending`, { credentials: "include" })
        .then(r => r.json())
        .then(data => {
          if (!data.reminders?.length) {
            setMessages(prev => [...prev, systemMsg("No pending reminders.\n\nTo set one, just tell Sparkbot: *\"Remind us about the standup daily at 9am\"*")])
            return
          }
          const lines = data.reminders.map((r: { id: string; message: string; fire_at: string; recurrence: string }) => {
            const recTag = r.recurrence !== "once" ? ` [${r.recurrence}]` : ""
            const fireAt = r.fire_at.slice(0, 16).replace("T", " ") + " UTC"
            return `⏰ \`${r.id.slice(0, 8)}\` ${fireAt}${recTag} — ${r.message}`
          }).join("\n")
          setMessages(prev => [...prev, systemMsg(`**Pending reminders (${data.count}):**\n\n${lines}\n\nTo cancel one, tell Sparkbot: *"Cancel reminder [id]"*`)])
        })
        .catch(() => setMessages(prev => [...prev, systemMsg("⚠️ Could not fetch reminders.")]))
      return true
    }

    if (cmd === "/meeting") {
      const sub = args.toLowerCase()

      if (sub === "start") {
        setMeeting({ active: true, startedAt: new Date(), notes: [], decisions: [], actions: [] })
        setMessages(prev => [...prev, systemMsg("**Meeting started.** I'll help capture notes, decisions, and action items.\n\nPrefix messages with:\n- `note:` — add a note\n- `decided:` — record a decision\n- `action:` — add an action item\n\nType **/meeting stop** when done, **/meeting notes** to see the draft.")])
        return true
      }

      if (sub === "stop") {
        if (!meeting.active) { setMessages(prev => [...prev, systemMsg("No meeting is active. Start one with **/meeting start**")]); return true }
        const notes = formatMeetingNotes(meeting)
        const blob = new Blob([notes], { type: "text/markdown" })
        const url = URL.createObjectURL(blob)
        const a = document.createElement("a"); a.href = url; a.download = `meeting-${new Date().toISOString().slice(0,10)}.md`; a.click()
        URL.revokeObjectURL(url)
        setMeeting(emptyMeeting())
        setMessages(prev => [...prev, systemMsg("**Meeting ended.** Notes exported as Markdown.")])
        return true
      }

      if (sub === "notes") {
        if (!meeting.active) { setMessages(prev => [...prev, systemMsg("No meeting is active.")]); return true }
        setMessages(prev => [...prev, systemMsg(formatMeetingNotes(meeting))])
        return true
      }

      setMessages(prev => [...prev, systemMsg("**Meeting commands:**\n- **/meeting start** — begin a meeting\n- **/meeting stop** — end and export notes\n- **/meeting notes** — preview current notes")])
      return true
    }

    return false
  }, [messages, meeting, formatMeetingNotes, agents])

  // ── Capture meeting items from messages ──────────────────────────────────────

  const captureMeetingItem = useCallback((content: string) => {
    if (!meeting.active) return
    const lower = content.toLowerCase()
    if (lower.startsWith("note:")) {
      setMeeting(prev => ({ ...prev, notes: [...prev.notes, content.slice(5).trim()] }))
    } else if (lower.startsWith("decided:") || lower.startsWith("decision:")) {
      const val = content.replace(/^decided?:/i, "").trim()
      setMeeting(prev => ({ ...prev, decisions: [...prev.decisions, val] }))
    } else if (lower.startsWith("action:")) {
      setMeeting(prev => ({ ...prev, actions: [...prev.actions, content.slice(7).trim()] }))
    }
  }, [meeting])

  // ── File upload ──────────────────────────────────────────────────────────────

  const handleFileUpload = useCallback(async (file: File) => {
    if (!roomId || uploading || sending) return
    setUploading(true)

    const tempHumanId = `temp-human-${Date.now()}`
    const tempBotId = `temp-bot-${Date.now()}`
    const isImage = file.type.startsWith("image/")
    const caption = inputValue.trim()
    setInputValue("")

    const humanContent = isImage
      ? `📷 ${file.name}${caption ? ` — ${caption}` : ""}`
      : `📎 ${file.name}${caption ? ` — ${caption}` : ""}`

    setMessages(prev => [
      ...prev,
      { id: tempHumanId, content: humanContent, created_at: new Date().toISOString(), sender_type: "HUMAN" },
      { id: tempBotId, content: "", created_at: new Date().toISOString(), sender_type: "BOT", isStreaming: true },
    ])

    try {
      const form = new FormData()
      form.append("file", file)
      form.append("caption", caption)

      const res = await fetch(`/api/v1/chat/rooms/${roomId}/upload`, {
        method: "POST",
        credentials: "include",
        body: form,
      })

      if (!res.ok || !res.body) {
        setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: "⚠️ Upload failed.", isStreaming: false } : m))
        setUploading(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n"); buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.type === "human_message") {
              // Update human message to show the actual image/file
              const fileContent = isImage
                ? `![${file.name}](/api/v1/chat/rooms/${roomId}/uploads/${ev.message_id}/${file.name})\n\n${caption}`
                : humanContent
              setMessages(prev => prev.map(m => m.id === tempHumanId ? { ...m, id: ev.message_id, content: fileContent } : m))
            } else if (ev.type === "token") {
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: m.content + ev.token } : m))
            } else if (ev.type === "done") {
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, id: ev.message_id, isStreaming: false } : m))
              if (ev.file_url && isImage) {
                setMessages(prev => prev.map(m =>
                  m.sender_type === "HUMAN" && m.content.startsWith("📷")
                    ? { ...m, content: `![${file.name}](${ev.file_url})${caption ? `\n\n${caption}` : ""}` }
                    : m
                ))
              }
            } else if (ev.type === "error") {
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: `⚠️ ${ev.error}`, isStreaming: false } : m))
            }
          } catch { /* ignore */ }
        }
      }
    } catch {
      setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: "⚠️ Upload error.", isStreaming: false } : m))
    } finally {
      setUploading(false)
    }
  }, [roomId, uploading, sending, inputValue])

  // ── Send ─────────────────────────────────────────────────────────────────────

  const handleSend = useCallback(async () => {
    const content = inputValue.trim()
    if (!content || !roomId || sending) return
    setInputValue("")
    setShowCommands(false)
    setShowAgentPicker(false)

    if (content.startsWith("/")) {
      if (handleCommand(content)) return
      setMessages(prev => [...prev, systemMsg(`Unknown command: **${content.split(" ")[0]}**\nType **/help** for available commands.`)])
      return
    }

    captureMeetingItem(content)
    setSending(true)

    const tempHumanId = `temp-human-${Date.now()}`
    const tempBotId = `temp-bot-${Date.now()}`
    setMessages(prev => [
      ...prev,
      { id: tempHumanId, content, created_at: new Date().toISOString(), sender_type: "HUMAN" },
      { id: tempBotId, content: "", created_at: new Date().toISOString(), sender_type: "BOT", isStreaming: true },
    ])

    try {
      const res = await fetch(`/api/v1/chat/rooms/${roomId}/messages/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ content }),
      })

      if (!res.ok || !res.body) {
        setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: "⚠️ Request failed.", isStreaming: false } : m))
        setSending(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n"); buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.type === "human_message") {
              setMessages(prev => prev.map(m => m.id === tempHumanId ? { ...m, id: ev.message_id } : m))
            } else if (ev.type === "tool_start") {
              const icon = TOOL_ICONS[ev.tool] ?? "⚙️"
              const label = ev.input?.query ?? ev.input?.expression ?? ""
              setMessages(prev => prev.map(m => m.id === tempBotId
                ? { ...m, toolActivity: `${icon} ${ev.tool.replace("_", " ")}${label ? `: ${label}` : ""}…` }
                : m))
            } else if (ev.type === "tool_done") {
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, toolActivity: undefined } : m))
            } else if (ev.type === "token") {
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: m.content + ev.token } : m))
            } else if (ev.type === "confirm_required") {
              // Pause streaming and show confirmation modal
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: "", isStreaming: false, toolActivity: undefined } : m))
              setPendingConfirm({ confirmId: ev.confirm_id, tool: ev.tool, input: ev.input ?? {} })
              setSending(false)
              return
            } else if (ev.type === "done") {
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, id: ev.message_id, isStreaming: false, toolActivity: undefined, agent: ev.agent } : m))
            } else if (ev.type === "error") {
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: `⚠️ ${ev.error}`, isStreaming: false, toolActivity: undefined } : m))
            }
          } catch { /* ignore */ }
        }
      }
    } catch {
      setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: "⚠️ Connection error.", isStreaming: false } : m))
    } finally {
      setSending(false)
    }
  }, [inputValue, roomId, sending, handleCommand, captureMeetingItem, agents])

  // ── Confirmation handlers ────────────────────────────────────────────────────

  const handleConfirm = useCallback(async () => {
    if (!pendingConfirm || !roomId) return
    const { confirmId } = pendingConfirm
    setPendingConfirm(null)
    setSending(true)
    const tempBotId = `temp-bot-confirm-${Date.now()}`
    setMessages(prev => [...prev,
      { id: tempBotId, content: "", created_at: new Date().toISOString(), sender_type: "BOT", isStreaming: true },
    ])
    try {
      const res = await fetch(`/api/v1/chat/rooms/${roomId}/messages/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ content: "", confirm_id: confirmId }),
      })
      if (!res.ok || !res.body) {
        setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: "⚠️ Confirmation failed.", isStreaming: false } : m))
        setSending(false); return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n"); buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.type === "token") setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: m.content + ev.token } : m))
            else if (ev.type === "done") setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, id: ev.message_id, isStreaming: false } : m))
            else if (ev.type === "error") setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: `⚠️ ${ev.error}`, isStreaming: false } : m))
          } catch { /* ignore */ }
        }
      }
    } catch {
      setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: "⚠️ Connection error.", isStreaming: false } : m))
    } finally { setSending(false) }
  }, [pendingConfirm, roomId])

  const handleCancel = useCallback(() => {
    setPendingConfirm(null)
    setMessages(prev => [...prev, systemMsg("Action cancelled.")])
  }, [])

  if (loading) {
    return <div className="flex h-screen items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
  }

  const isBot    = (m: Message) => String(m.sender_type ?? "").toUpperCase() === "BOT"
  const isSystem = (m: Message) => m.isSystem === true
  const isOwn    = (m: Message) => !isBot(m) && !isSystem(m)

  return (
    <div className="relative flex h-screen flex-col">
      {/* Confirmation modal */}
      {pendingConfirm && (
        <ConfirmModal pending={pendingConfirm} onConfirm={handleConfirm} onCancel={handleCancel} />
      )}

      <SparkbotSettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        room={roomInfo}
        loading={settingsLoading}
        savingExecution={savingExecution}
        policyEntries={policyEntries}
        guardianTasks={guardianTasks}
        guardianRuns={guardianRuns}
        taskName={taskName}
        taskToolName={taskToolName}
        taskSchedule={taskSchedule}
        taskArgs={taskArgs}
        taskSaving={taskSaving}
        error={settingsError}
        onRefresh={refreshControls}
        onToggleExecution={toggleExecutionGate}
        onTaskNameChange={setTaskName}
        onTaskToolChange={setTaskToolName}
        onTaskScheduleChange={setTaskSchedule}
        onTaskArgsChange={setTaskArgs}
        onCreateTask={createGuardianTask}
        onToggleTask={setGuardianTaskState}
        onRunTask={runGuardianTask}
      />

      {/* Search overlay */}
      {showSearch && roomId && (
        <SearchPanel roomId={roomId} onClose={() => setShowSearch(false)} />
      )}

      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3 shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold select-none">S</div>
          <div>
            <h1 className="text-sm font-semibold flex items-center gap-2">
              Sparkbot
              {meeting.active && (
                <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-semibold text-red-500">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
                  MEETING
                </span>
              )}
            </h1>
            <p className="text-xs text-muted-foreground">Sparkpit Labs · type /help for commands</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setSettingsOpen(true)} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" title="Sparkbot controls">
            <Settings2 className="size-4" />
          </button>
          <button onClick={() => setShowSearch(true)} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" title="Search messages">
            <Search className="size-4" />
          </button>
          <button onClick={() => {
            localStorage.removeItem("access_token")
            sessionStorage.removeItem("chat_auth")
            fetch("/api/v1/chat/users/session", { method: "DELETE", credentials: "include" }).finally(() => { window.location.href = "/login" })
          }} className="text-sm text-muted-foreground hover:text-foreground">
            Logout
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-auto px-4 py-4 space-y-2">
        {messages.length === 0 ? (
          <p className="text-center text-muted-foreground text-sm py-8">
            No messages yet — say hello, or type <span className="font-mono">/help</span>
          </p>
        ) : (
          messages.map(msg => {
            if (isSystem(msg)) {
              return (
                <div key={msg.id} className="flex justify-center">
                  <div className="max-w-[80%] rounded-lg border border-dashed bg-muted/30 px-4 py-2">
                    <BotMessage content={msg.content} />
                  </div>
                </div>
              )
            }
            const own = isOwn(msg)
            return (
              <div key={msg.id} className={`flex ${own ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[75%] rounded-2xl px-4 py-2 ${own ? "rounded-br-md bg-primary text-primary-foreground" : "rounded-bl-md bg-muted"}`}>
                  {isBot(msg)
                    ? <BotMessage content={msg.content} isStreaming={msg.isStreaming} toolActivity={msg.toolActivity} agent={msg.agent} />
                    : <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>
                  }
                  <p className={`text-[10px] mt-1 opacity-70 ${own ? "text-right" : ""}`}>
                    {new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    {msg.isStreaming && " · typing…"}
                  </p>
                </div>
              </div>
            )
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t px-4 py-3 shrink-0">
        <div className="relative flex items-center gap-2">
          {showCommands && (
            <CommandPicker query={inputValue} onSelect={cmd => { setInputValue(cmd); inputRef.current?.focus() }} />
          )}
          {showAgentPicker && (
            <AgentPicker
              query={inputValue}
              agents={agents}
              onSelect={name => { setInputValue(`@${name} `); setShowAgentPicker(false); inputRef.current?.focus() }}
            />
          )}

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,application/pdf,.txt,.md,.csv,.json"
            className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); e.target.value = "" }}
          />

          {/* Upload button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={sending || uploading}
            className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground hover:bg-muted disabled:opacity-40"
            title="Attach file or image"
          >
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
          </button>

          <input
            ref={inputRef}
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend() }
              if (e.key === "Escape") setShowCommands(false)
            }}
            placeholder={meeting.active ? "note: / decided: / action: or ask a question…" : "Message Sparkbot… or / for commands"}
            className="flex-1 rounded-full border bg-muted/40 px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-ring/30"
            disabled={sending || uploading}
          />
          <button
            onClick={handleSend}
            disabled={sending || uploading || !inputValue.trim()}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground disabled:opacity-40"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}

export default SparkbotDmPage
