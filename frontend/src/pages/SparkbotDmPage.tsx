// Sparkbot DM Page — streaming, slash commands, syntax highlighting, search, meeting mode

import { useState, useEffect, useCallback, useRef } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { Check, CornerUpLeft, Copy, Loader2, Mic, Paperclip, Pencil, RefreshCw, Search, Send, Settings2, Volume2, VolumeX, X } from "lucide-react"
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
  reply_to_id?: string    // threading: parent message id
  is_edited?: boolean     // true after inline edit saved
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

interface ControlsDashboardSummary {
  summary: {
    pending_approvals: number
    guardian_jobs: number
    guardian_jobs_enabled: number
    token_guardian_mode: string
  }
  today: {
    token_guardian: {
      mode: string
      live_ready: boolean
      configured_models: string[]
      allowed_live_models: string[]
      last_route: {
        created_at: string
        classification: string | null
        current_model: string | null
        selected_model: string | null
        applied_model: string | null
        fallback_reason: string | null
      } | null
    }
  }
}

interface ModelsControlsConfig {
  active_model: string
  token_guardian_mode: string
  stack: {
    primary: string
    backup_1: string
    backup_2: string
    heavy_hitter: string
  }
  providers: Array<{
    id: string
    label: string
    configured: boolean
    models: string[]
  }>
  comms: {
    telegram: {
      configured: boolean
      poll_enabled: boolean
      private_only: boolean
      linked_chats: number
    }
    discord: {
      configured: boolean
      enabled: boolean
      dm_only: boolean
      linked_channels: number
    }
    whatsapp: {
      configured: boolean
      enabled: boolean
      linked_numbers: number
    }
    github: {
      configured: boolean
      enabled: boolean
      bot_login: string
      default_repo: string
      allowed_repos: string[]
      allowed_repos_count: number
      linked_threads: number
      webhook_path: string
    }
  }
  notices: string[]
  restart_required?: boolean
}

interface ModelStackForm {
  primary: string
  backup_1: string
  backup_2: string
  heavy_hitter: string
}

interface ProviderTokenDrafts {
  openai_api_key: string
  anthropic_api_key: string
  google_api_key: string
  groq_api_key: string
  minimax_api_key: string
}

interface CommsForm {
  telegram: {
    bot_token: string
    enabled: boolean
    private_only: boolean
  }
  discord: {
    bot_token: string
    enabled: boolean
    dm_only: boolean
  }
  whatsapp: {
    token: string
    phone_id: string
    verify_token: string
    enabled: boolean
  }
  github: {
    token: string
    webhook_secret: string
    bot_login: string
    default_repo: string
    allowed_repos: string
    enabled: boolean
  }
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
  dashboardSummary: ControlsDashboardSummary | null
  modelsConfig: ModelsControlsConfig | null
  modelStack: ModelStackForm
  providerDrafts: ProviderTokenDrafts
  commsForm: CommsForm
  savingModelStack: boolean
  savingProviderTokens: boolean
  savingComms: boolean
  tokenGuardianMode: string
  savingTokenGuardianMode: boolean
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
  onModelStackChange: (field: keyof ModelStackForm, value: string) => void
  onProviderDraftChange: (field: keyof ProviderTokenDrafts, value: string) => void
  onCommsTextChange: (section: keyof CommsForm, field: string, value: string) => void
  onCommsToggleChange: (section: keyof CommsForm, field: string, value: boolean) => void
  onSaveModelStack: () => void
  onSaveProviderTokens: () => void
  onSaveComms: () => void
  onTokenGuardianModeChange: (value: string) => void
  onSaveTokenGuardianMode: () => void
  onTaskNameChange: (value: string) => void
  onTaskToolChange: (value: string) => void
  onTaskScheduleChange: (value: string) => void
  onTaskArgsChange: (value: string) => void
  onCreateTask: () => void
  onToggleTask: (taskId: string, enabled: boolean) => void
  onRunTask: (taskId: string) => void
}

const TASK_TOOL_OPTIONS = [
  "morning_briefing",
  "gmail_fetch_inbox",
  "gmail_search",
  "github_list_prs",
  "github_get_ci_status",
  "calendar_list_events",
  "calendar_create_event",
  "news_headlines",
  "crypto_price",
  "currency_convert",
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
  dashboardSummary,
  modelsConfig,
  modelStack,
  providerDrafts,
  commsForm,
  savingModelStack,
  savingProviderTokens,
  savingComms,
  tokenGuardianMode,
  savingTokenGuardianMode,
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
  onModelStackChange,
  onProviderDraftChange,
  onCommsTextChange,
  onCommsToggleChange,
  onSaveModelStack,
  onSaveProviderTokens,
  onSaveComms,
  onTokenGuardianModeChange,
  onSaveTokenGuardianMode,
  onTaskNameChange,
  onTaskToolChange,
  onTaskScheduleChange,
  onTaskArgsChange,
  onCreateTask,
  onToggleTask,
  onRunTask,
}: SparkbotSettingsDialogProps) {
  const configuredProviderCount = modelsConfig?.providers.filter((provider) => provider.configured).length ?? 0
  const enabledChannelCount = [
    Boolean(commsForm.telegram.enabled && modelsConfig?.comms.telegram.configured),
    Boolean(commsForm.discord.enabled && modelsConfig?.comms.discord.configured),
    Boolean(commsForm.whatsapp.enabled && modelsConfig?.comms.whatsapp.configured),
    Boolean(commsForm.github.enabled && modelsConfig?.comms.github.configured),
  ].filter(Boolean).length
  const onboardingSteps = [
    {
      title: "Connect one AI provider",
      done: configuredProviderCount > 0,
      detail: configuredProviderCount > 0
        ? `${configuredProviderCount} provider${configuredProviderCount === 1 ? "" : "s"} configured`
        : "Paste one token below so Sparkbot can respond",
    },
    {
      title: "Pick your model stack",
      done: Boolean(modelStack.primary && modelStack.heavy_hitter),
      detail: modelStack.primary
        ? `Primary: ${modelStack.primary}`
        : "Choose a primary model and a heavy hitter",
    },
    {
      title: "Turn on one channel",
      done: enabledChannelCount > 0,
      detail: enabledChannelCount > 0
        ? `${enabledChannelCount} channel${enabledChannelCount === 1 ? "" : "s"} enabled`
        : "Enable Telegram, Discord, WhatsApp, or GitHub after adding credentials",
    },
    {
      title: "Keep write actions gated",
      done: !room?.execution_allowed,
      detail: room?.execution_allowed
        ? "Execution gate is on for this room. Turn it off unless you need machine operations."
        : "Recommended default for personal use: execution gate stays off",
    },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Sparkbot Controls</DialogTitle>
          <DialogDescription>
            Room execution gate, function routing, dashboard access, and Task Guardian schedules.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          <section className="rounded-xl border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">Consumer onboarding</h2>
                <p className="text-xs text-muted-foreground">
                  Get Sparkbot ready for daily personal use without leaving this panel.
                </p>
              </div>
              <div className="rounded-full bg-muted px-3 py-1 text-[11px] font-medium text-muted-foreground">
                {onboardingSteps.filter((step) => step.done).length}/{onboardingSteps.length} ready
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {onboardingSteps.map((step, index) => (
                <div key={step.title} className="rounded-lg bg-muted/40 px-3 py-3">
                  <div className="flex items-center gap-2">
                    <div className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold ${step.done ? "bg-emerald-500/15 text-emerald-600" : "bg-background text-muted-foreground"}`}>
                      {step.done ? <Check className="size-3.5" /> : index + 1}
                    </div>
                    <div className="text-sm font-medium">{step.title}</div>
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">{step.detail}</div>
                </div>
              ))}
            </div>

            <div className="mt-4 grid gap-3 lg:grid-cols-3">
              <div className="rounded-lg border bg-background/60 px-3 py-3">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Start here</div>
                <div className="mt-2 space-y-1.5 text-xs">
                  <div className="flex gap-2"><span className="font-semibold text-primary shrink-0">1.</span> Paste one provider token (below) and save it.</div>
                  <div className="flex gap-2"><span className="font-semibold text-primary shrink-0">2.</span> Pick your model stack — primary for everyday chat, heavy hitter for long tasks.</div>
                  <div className="flex gap-2"><span className="font-semibold text-primary shrink-0">3.</span> Enable one comms channel so reminders reach you on Telegram, Discord, or WhatsApp.</div>
                  <div className="flex gap-2"><span className="font-semibold text-primary shrink-0">4.</span> Ask for a morning brief, set a reminder, or search your inbox.</div>
                </div>
              </div>
              <div className="rounded-lg border bg-background/60 px-3 py-3">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Good first prompts</div>
                <div className="mt-2 space-y-2 text-xs text-muted-foreground">
                  <div><code className="rounded bg-muted px-1 py-0.5">Give me a morning brief for today.</code></div>
                  <div><code className="rounded bg-muted px-1 py-0.5">Remind me every weekday at 8am to check priorities.</code></div>
                  <div><code className="rounded bg-muted px-1 py-0.5">Summarize my unread inbox.</code></div>
                  <div><code className="rounded bg-muted px-1 py-0.5">What's the price of bitcoin right now?</code></div>
                  <div><code className="rounded bg-muted px-1 py-0.5">Show me anything waiting on my approval.</code></div>
                </div>
              </div>
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-50/30 dark:bg-emerald-950/20 px-3 py-3">
                <div className="text-[11px] uppercase tracking-wide text-emerald-700 dark:text-emerald-400">How Sparkbot protects you</div>
                <div className="mt-2 space-y-2 text-xs text-muted-foreground">
                  <div>
                    <span className="font-medium text-foreground">Write actions always confirm.</span>{" "}
                    Sending email, posting to Slack, or creating calendar events always shows a modal — Sparkbot cannot act without your approval.
                  </div>
                  <div>
                    <span className="font-medium text-foreground">Execution gate = opt-in only.</span>{" "}
                    Server commands and SSH tools are disabled by default. Turn on the room execution gate only when you need them.
                  </div>
                  <div>
                    <span className="font-medium text-foreground">Token Guardian shadow mode</span>{" "}
                    observes routing decisions silently — it never switches models on its own until you flip to live mode.
                  </div>
                </div>
              </div>
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
          <section className="rounded-xl border p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">Room execution gate</h2>
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
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">System health</h2>
                <p className="text-xs text-muted-foreground">
                  Live status of every Sparkbot subsystem at a glance.
                </p>
              </div>
              <button
                type="button"
                onClick={onRefresh}
                className="rounded-md border px-3 py-1.5 text-xs hover:bg-muted"
              >
                <span className="inline-flex items-center gap-1"><RefreshCw className="size-3" /> Refresh</span>
              </button>
            </div>

            {/* Health tiles */}
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {/* LLM */}
              <div className={`rounded-lg px-3 py-3 ${configuredProviderCount > 0 ? "bg-emerald-50/50 dark:bg-emerald-950/30 border border-emerald-500/20" : "bg-amber-50/50 dark:bg-amber-950/30 border border-amber-500/20"}`}>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">LLM</div>
                <div className={`mt-1 text-sm font-semibold ${configuredProviderCount > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}`}>
                  {configuredProviderCount > 0 ? `${configuredProviderCount} provider${configuredProviderCount > 1 ? "s" : ""}` : "No provider"}
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground truncate">
                  {modelStack.primary || "No model selected"}
                </div>
              </div>

              {/* Task Guardian */}
              {(() => {
                const enabledCount = guardianTasks.filter(t => t.enabled).length
                const lastRun = guardianRuns[0]
                const lastOk = lastRun ? lastRun.status === "success" : null
                return (
                  <div className={`rounded-lg px-3 py-3 ${enabledCount > 0 ? "bg-emerald-50/50 dark:bg-emerald-950/30 border border-emerald-500/20" : "bg-muted/40 border"}`}>
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Task Guardian</div>
                    <div className={`mt-1 text-sm font-semibold ${enabledCount > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground"}`}>
                      {enabledCount}/{guardianTasks.length} active
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {lastRun ? (
                        <span className={lastOk ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"}>
                          Last: {lastRun.status}
                        </span>
                      ) : "No runs yet"}
                    </div>
                  </div>
                )
              })()}

              {/* Token Guardian */}
              {(() => {
                const mode = dashboardSummary?.summary.token_guardian_mode ?? tokenGuardianMode ?? "off"
                const liveReady = dashboardSummary?.today.token_guardian.live_ready
                return (
                  <div className={`rounded-lg px-3 py-3 ${mode === "live" ? "bg-emerald-50/50 dark:bg-emerald-950/30 border border-emerald-500/20" : mode === "shadow" ? "bg-sky-50/50 dark:bg-sky-950/30 border border-sky-500/20" : "bg-muted/40 border"}`}>
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Token Guardian</div>
                    <div className={`mt-1 text-sm font-semibold capitalize ${mode === "live" ? "text-emerald-700 dark:text-emerald-400" : mode === "shadow" ? "text-sky-700 dark:text-sky-400" : "text-muted-foreground"}`}>
                      {mode}
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {mode === "shadow" ? "Observing — no auto-routing" : mode === "live" ? (liveReady ? "Live routing active" : "No targets configured") : "Routing disabled"}
                    </div>
                    <div className="mt-2 flex gap-1.5">
                      <select
                        value={tokenGuardianMode}
                        onChange={(e) => onTokenGuardianModeChange(e.target.value)}
                        className="flex-1 rounded border bg-background px-1.5 py-1 text-xs outline-none"
                      >
                        <option value="off">Off</option>
                        <option value="shadow">Shadow</option>
                        <option value="live">Live</option>
                      </select>
                      <button
                        type="button"
                        onClick={onSaveTokenGuardianMode}
                        disabled={savingTokenGuardianMode}
                        className="rounded bg-primary px-2 py-1 text-[11px] text-primary-foreground disabled:opacity-50"
                      >
                        {savingTokenGuardianMode ? "…" : "Apply"}
                      </button>
                    </div>
                  </div>
                )
              })()}

              {/* Comms + Approvals */}
              <div className={`rounded-lg px-3 py-3 ${enabledChannelCount > 0 ? "bg-emerald-50/50 dark:bg-emerald-950/30 border border-emerald-500/20" : "bg-muted/40 border"}`}>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Comms</div>
                <div className={`mt-1 text-sm font-semibold ${enabledChannelCount > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground"}`}>
                  {enabledChannelCount > 0 ? `${enabledChannelCount} channel${enabledChannelCount > 1 ? "s" : ""}` : "None enabled"}
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {(() => {
                    const pending = dashboardSummary?.summary.pending_approvals ?? 0
                    return pending > 0
                      ? <span className="text-amber-600 dark:text-amber-400 font-medium">{pending} pending approval{pending > 1 ? "s" : ""}</span>
                      : "No pending approvals"
                  })()}
                </div>
              </div>
            </div>
          </section>
          </div>

          <section className="rounded-xl border p-4">
            <div className="mb-3">
              <h2 className="text-sm font-semibold">Function routing</h2>
              <p className="text-xs text-muted-foreground">
                Token Guardian model routing is global. This room gate still separately controls machine operations.
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg bg-muted/40 px-3 py-3">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Mode</div>
                <select
                  value={tokenGuardianMode}
                  onChange={(e) => onTokenGuardianModeChange(e.target.value)}
                  className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                >
                  <option value="off">Off</option>
                  <option value="shadow">Shadow</option>
                  <option value="live">Live</option>
                </select>
                <div className="mt-1 text-xs text-muted-foreground">
                  {dashboardSummary?.today.token_guardian.live_ready ? "Live-ready" : "No live route targets configured"}
                </div>
              </div>
              <div className="rounded-lg bg-muted/40 px-3 py-3">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Allowed models</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {dashboardSummary?.today.token_guardian.allowed_live_models.join(", ") || "None"}
                </div>
              </div>
            </div>
            <div className="mt-3 rounded-lg bg-muted/40 px-3 py-3">
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Last route</div>
              {dashboardSummary?.today.token_guardian.last_route ? (
                <div className="mt-1 space-y-1 text-xs text-muted-foreground">
                  <div>
                    {dashboardSummary.today.token_guardian.last_route.current_model || "unknown"} →{" "}
                    <span className="font-medium text-foreground">
                      {dashboardSummary.today.token_guardian.last_route.applied_model || "unknown"}
                    </span>
                  </div>
                  <div>
                    {dashboardSummary.today.token_guardian.last_route.classification || "general"} ·{" "}
                    {new Date(dashboardSummary.today.token_guardian.last_route.created_at).toLocaleString()}
                  </div>
                  <div>
                    Requested {dashboardSummary.today.token_guardian.last_route.selected_model || "unknown"}
                  </div>
                  {dashboardSummary.today.token_guardian.last_route.fallback_reason ? (
                    <div>{dashboardSummary.today.token_guardian.last_route.fallback_reason}</div>
                  ) : null}
                </div>
              ) : (
                <div className="mt-1 text-xs text-muted-foreground">
                  No routed request recorded yet.
                </div>
              )}
            </div>
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={onSaveTokenGuardianMode}
                disabled={savingTokenGuardianMode}
                className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
              >
                {savingTokenGuardianMode ? "Saving..." : "Save routing mode"}
              </button>
            </div>
          </section>

          <section className="rounded-xl border p-4">
            <div className="mb-3">
              <h2 className="text-sm font-semibold">Models</h2>
              <p className="text-xs text-muted-foreground">
                Set Sparkbot&apos;s primary model, backup chain, and heavy hitter for harder work.
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {[
                ["primary", "Primary"],
                ["backup_1", "1st backup"],
                ["backup_2", "2nd backup"],
                ["heavy_hitter", "Heavy hitter"],
              ].map(([field, label]) => (
                <label key={field} className="space-y-1">
                  <div className="text-xs font-medium text-muted-foreground">{label}</div>
                  <select
                    value={modelStack[field as keyof ModelStackForm]}
                    onChange={(e) => onModelStackChange(field as keyof ModelStackForm, e.target.value)}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                  >
                    {Array.from(new Set(modelsConfig?.providers.flatMap((provider) => provider.models) ?? [])).map((model) => (
                      <option key={model} value={model}>{model}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between gap-3">
              <div className="text-xs text-muted-foreground">
                Active now: <span className="font-medium text-foreground">{modelsConfig?.active_model ?? "unknown"}</span>
              </div>
              <button
                type="button"
                onClick={onSaveModelStack}
                disabled={savingModelStack}
                className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
              >
                {savingModelStack ? "Saving..." : "Save model stack"}
              </button>
            </div>
          </section>

          <section className="rounded-xl border p-4">
            <div className="mb-3">
              <h2 className="text-sm font-semibold">Provider onboarding</h2>
              <p className="text-xs text-muted-foreground">
                Paste API tokens once, then choose the matching models above. Tokens are never read back into the UI.
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {modelsConfig?.providers.map((provider) => {
                const field = `${provider.id}_api_key` as keyof ProviderTokenDrafts
                return (
                  <div key={provider.id} className="rounded-lg border bg-muted/40 px-3 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-medium">{provider.label}</div>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${provider.configured ? "bg-emerald-500/15 text-emerald-600" : "bg-muted text-muted-foreground"}`}>
                        {provider.configured ? "Configured" : "Missing"}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {provider.models.join(", ")}
                    </div>
                    <input
                      type="password"
                      value={providerDrafts[field]}
                      onChange={(e) => onProviderDraftChange(field, e.target.value)}
                      placeholder={`Paste ${provider.label} token`}
                      className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                    />
                  </div>
                )
              })}
            </div>
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={onSaveProviderTokens}
                disabled={savingProviderTokens}
                className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
              >
                {savingProviderTokens ? "Saving..." : "Save provider tokens"}
              </button>
            </div>
          </section>

          <section className="rounded-xl border p-4">
            <div className="mb-3">
              <h2 className="text-sm font-semibold">Comms</h2>
              <p className="text-xs text-muted-foreground">
                Configure Telegram, Discord, WhatsApp, and GitHub from the same control panel. Bridge startup changes require a service restart.
              </p>
            </div>
            <div className="grid gap-4 lg:grid-cols-4">
              <div className="rounded-lg border bg-muted/40 px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium">Telegram</div>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${modelsConfig?.comms.telegram.configured ? "bg-emerald-500/15 text-emerald-600" : "bg-muted text-muted-foreground"}`}>
                    {modelsConfig?.comms.telegram.configured ? "Configured" : "Missing"}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">Linked chats: {modelsConfig?.comms.telegram.linked_chats ?? 0}</div>
                <input
                  type="password"
                  value={commsForm.telegram.bot_token}
                  onChange={(e) => onCommsTextChange("telegram", "bot_token", e.target.value)}
                  placeholder="Paste Telegram bot token"
                  className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                />
                <label className="mt-3 flex items-center justify-between gap-2 text-xs">
                  <span>Enable polling</span>
                  <input
                    type="checkbox"
                    checked={commsForm.telegram.enabled}
                    onChange={(e) => onCommsToggleChange("telegram", "enabled", e.target.checked)}
                  />
                </label>
                <label className="mt-2 flex items-center justify-between gap-2 text-xs">
                  <span>Private only</span>
                  <input
                    type="checkbox"
                    checked={commsForm.telegram.private_only}
                    onChange={(e) => onCommsToggleChange("telegram", "private_only", e.target.checked)}
                  />
                </label>
              </div>

              <div className="rounded-lg border bg-muted/40 px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium">Discord</div>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${modelsConfig?.comms.discord.configured ? "bg-emerald-500/15 text-emerald-600" : "bg-muted text-muted-foreground"}`}>
                    {modelsConfig?.comms.discord.configured ? "Configured" : "Missing"}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">Linked channels: {modelsConfig?.comms.discord.linked_channels ?? 0}</div>
                <input
                  type="password"
                  value={commsForm.discord.bot_token}
                  onChange={(e) => onCommsTextChange("discord", "bot_token", e.target.value)}
                  placeholder="Paste Discord bot token"
                  className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                />
                <label className="mt-3 flex items-center justify-between gap-2 text-xs">
                  <span>Enable bridge</span>
                  <input
                    type="checkbox"
                    checked={commsForm.discord.enabled}
                    onChange={(e) => onCommsToggleChange("discord", "enabled", e.target.checked)}
                  />
                </label>
                <label className="mt-2 flex items-center justify-between gap-2 text-xs">
                  <span>DM only</span>
                  <input
                    type="checkbox"
                    checked={commsForm.discord.dm_only}
                    onChange={(e) => onCommsToggleChange("discord", "dm_only", e.target.checked)}
                  />
                </label>
              </div>

              <div className="rounded-lg border bg-muted/40 px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium">WhatsApp</div>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${modelsConfig?.comms.whatsapp.configured ? "bg-emerald-500/15 text-emerald-600" : "bg-muted text-muted-foreground"}`}>
                    {modelsConfig?.comms.whatsapp.configured ? "Configured" : "Missing"}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">Linked numbers: {modelsConfig?.comms.whatsapp.linked_numbers ?? 0}</div>
                <input
                  type="password"
                  value={commsForm.whatsapp.token}
                  onChange={(e) => onCommsTextChange("whatsapp", "token", e.target.value)}
                  placeholder="Paste WhatsApp token"
                  className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                />
                <input
                  type="text"
                  value={commsForm.whatsapp.phone_id}
                  onChange={(e) => onCommsTextChange("whatsapp", "phone_id", e.target.value)}
                  placeholder="WhatsApp phone ID"
                  className="mt-2 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                />
                <input
                  type="text"
                  value={commsForm.whatsapp.verify_token}
                  onChange={(e) => onCommsTextChange("whatsapp", "verify_token", e.target.value)}
                  placeholder="Verify token"
                  className="mt-2 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                />
                <label className="mt-3 flex items-center justify-between gap-2 text-xs">
                  <span>Enable bridge</span>
                  <input
                    type="checkbox"
                    checked={commsForm.whatsapp.enabled}
                    onChange={(e) => onCommsToggleChange("whatsapp", "enabled", e.target.checked)}
                  />
                </label>
              </div>

              <div className="rounded-lg border bg-muted/40 px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium">GitHub</div>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${modelsConfig?.comms.github.configured ? "bg-emerald-500/15 text-emerald-600" : "bg-muted text-muted-foreground"}`}>
                    {modelsConfig?.comms.github.configured ? "Configured" : "Missing"}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">Linked threads: {modelsConfig?.comms.github.linked_threads ?? 0}</div>
                <div className="mt-1 text-xs text-muted-foreground">Webhook: {modelsConfig?.comms.github.webhook_path ?? "/api/v1/chat/github/events"}</div>
                <input
                  type="password"
                  value={commsForm.github.token}
                  onChange={(e) => onCommsTextChange("github", "token", e.target.value)}
                  placeholder="Paste GitHub token"
                  className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                />
                <input
                  type="password"
                  value={commsForm.github.webhook_secret}
                  onChange={(e) => onCommsTextChange("github", "webhook_secret", e.target.value)}
                  placeholder="Webhook secret"
                  className="mt-2 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                />
                <input
                  type="text"
                  value={commsForm.github.bot_login}
                  onChange={(e) => onCommsTextChange("github", "bot_login", e.target.value)}
                  placeholder="Bot login"
                  className="mt-2 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                />
                <input
                  type="text"
                  value={commsForm.github.default_repo}
                  onChange={(e) => onCommsTextChange("github", "default_repo", e.target.value)}
                  placeholder="Default repo (owner/repo)"
                  className="mt-2 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                />
                <input
                  type="text"
                  value={commsForm.github.allowed_repos}
                  onChange={(e) => onCommsTextChange("github", "allowed_repos", e.target.value)}
                  placeholder="Allowed repos (comma-separated)"
                  className="mt-2 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                />
                <label className="mt-3 flex items-center justify-between gap-2 text-xs">
                  <span>Enable bridge</span>
                  <input
                    type="checkbox"
                    checked={commsForm.github.enabled}
                    onChange={(e) => onCommsToggleChange("github", "enabled", e.target.checked)}
                  />
                </label>
                <div className="mt-4 rounded-lg border bg-background/70 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground">GitHub onboarding</div>
                  <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                    <div>1. Paste a GitHub token and a webhook secret, then save comms.</div>
                    <div>2. In your repo, add a webhook to <code className="rounded bg-muted px-1 py-0.5">{modelsConfig?.comms.github.webhook_path ?? "/api/v1/chat/github/events"}</code>.</div>
                    <div>3. Select <span className="font-medium text-foreground">Issue comments</span> and <span className="font-medium text-foreground">Pull request review comments</span>.</div>
                    <div>4. Restart <code className="rounded bg-muted px-1 py-0.5">sparkbot-v2</code>, then test in a thread with <code className="rounded bg-muted px-1 py-0.5">/sparkbot summarize this PR</code>.</div>
                  </div>
                  <div className="mt-3 rounded-md bg-muted/50 px-2 py-2 text-[11px] text-muted-foreground">
                    Replies in-thread support <code className="rounded bg-background px-1 py-0.5">approve</code> and <code className="rounded bg-background px-1 py-0.5">deny</code> for pending actions.
                  </div>
                  {modelsConfig?.comms.github.allowed_repos_count ? (
                    <div className="mt-2 text-[11px] text-muted-foreground">
                      Allowlisted repos: {modelsConfig.comms.github.allowed_repos.join(", ")}
                    </div>
                  ) : (
                    <div className="mt-2 text-[11px] text-amber-600">
                      No repo allowlist set. Add one if you want the bridge limited to specific repositories.
                    </div>
                  )}
                </div>
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3">
              <div className="text-xs text-muted-foreground">
                Save comms first, then restart `sparkbot-v2` to apply bridge startup changes.
              </div>
              <button
                type="button"
                onClick={onSaveComms}
                disabled={savingComms}
                className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
              >
                {savingComms ? "Saving..." : "Save comms"}
              </button>
            </div>
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
  const [controlsDashboard, setControlsDashboard] = useState<ControlsDashboardSummary | null>(null)
  const [modelsConfig, setModelsConfig] = useState<ModelsControlsConfig | null>(null)
  const [tokenGuardianMode, setTokenGuardianMode] = useState("shadow")
  const [savingTokenGuardianMode, setSavingTokenGuardianMode] = useState(false)
  const [modelStack, setModelStack] = useState<ModelStackForm>({
    primary: "gpt-4o-mini",
    backup_1: "gpt-4o",
    backup_2: "claude-sonnet-4-5",
    heavy_hitter: "gpt-4o",
  })
  const [providerDrafts, setProviderDrafts] = useState<ProviderTokenDrafts>({
    openai_api_key: "",
    anthropic_api_key: "",
    google_api_key: "",
    groq_api_key: "",
    minimax_api_key: "",
  })
  const [commsForm, setCommsForm] = useState<CommsForm>({
    telegram: { bot_token: "", enabled: true, private_only: true },
    discord: { bot_token: "", enabled: false, dm_only: false },
    whatsapp: { token: "", phone_id: "", verify_token: "sparkbot-wa-verify", enabled: false },
    github: {
      token: "",
      webhook_secret: "",
      bot_login: "sparkbot",
      default_repo: "",
      allowed_repos: "",
      enabled: false,
    },
  })
  const [savingModelStack, setSavingModelStack] = useState(false)
  const [savingProviderTokens, setSavingProviderTokens] = useState(false)
  const [savingComms, setSavingComms] = useState(false)
  const [policyEntries, setPolicyEntries] = useState<PolicyEntry[]>([])
  const [guardianTasks, setGuardianTasks] = useState<GuardianTaskRecord[]>([])
  const [guardianRuns, setGuardianRuns] = useState<GuardianRunRecord[]>([])
  const [taskName, setTaskName] = useState("")
  const [taskToolName, setTaskToolName] = useState("gmail_fetch_inbox")
  const [taskSchedule, setTaskSchedule] = useState("every:3600")
  const [taskArgs, setTaskArgs] = useState('{"max_emails": 5, "unread_only": true}')
  const [taskSaving, setTaskSaving] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const [voiceMode, setVoiceMode] = useState(
    () => localStorage.getItem("sparkbot_voice_mode") === "true"
  )
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const recordingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Reply / edit state ───────────────────────────────────────────────────────
  const [replyingTo, setReplyingTo] = useState<Message | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editContent, setEditContent] = useState("")

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages])
  useEffect(() => { setShowCommands(inputValue.startsWith("/") && !inputValue.includes(" ")) }, [inputValue])
  useEffect(() => { setShowAgentPicker(inputValue.startsWith("@") && !inputValue.includes(" ")) }, [inputValue])

  const applyControlsConfig = useCallback((config: ModelsControlsConfig) => {
    setModelsConfig(config)
    setTokenGuardianMode(config.token_guardian_mode || "shadow")
    setModelStack(config.stack)
    setCommsForm({
      telegram: {
        bot_token: "",
        enabled: Boolean(config.comms.telegram.poll_enabled),
        private_only: Boolean(config.comms.telegram.private_only),
      },
      discord: {
        bot_token: "",
        enabled: Boolean(config.comms.discord.enabled),
        dm_only: Boolean(config.comms.discord.dm_only),
      },
      whatsapp: {
        token: "",
        phone_id: "",
        verify_token: "sparkbot-wa-verify",
        enabled: Boolean(config.comms.whatsapp.enabled),
      },
      github: {
        token: "",
        webhook_secret: "",
        bot_login: config.comms.github.bot_login || "sparkbot",
        default_repo: config.comms.github.default_repo || "",
        allowed_repos: (config.comms.github.allowed_repos ?? []).join(", "),
        enabled: Boolean(config.comms.github.enabled),
      },
    })
  }, [])

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
      const [roomRes, policyRes, tasksRes, runsRes, dashboardRes, modelsConfigRes] = await Promise.all([
        fetch(`/api/v1/chat/rooms/${roomId}`, { credentials: "include" }),
        fetch(`/api/v1/chat/audit?limit=10&room_id=${roomId}&tool=policy_decision`, { credentials: "include" }),
        fetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks?limit=20`, { credentials: "include" }),
        fetch(`/api/v1/chat/rooms/${roomId}/guardian/runs?limit=10`, { credentials: "include" }),
        fetch("/api/v1/chat/dashboard/summary", { credentials: "include" }),
        fetch("/api/v1/chat/models/config", { credentials: "include" }),
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
      if (dashboardRes.ok) {
        setControlsDashboard(await dashboardRes.json())
      }
      if (modelsConfigRes.ok) {
        applyControlsConfig(await modelsConfigRes.json())
      }
    } catch {
      setSettingsError("Could not load Sparkbot controls.")
    } finally {
      setSettingsLoading(false)
    }
  }, [roomId, applyControlsConfig])

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

  const saveModelStack = useCallback(async () => {
    setSavingModelStack(true)
    setSettingsError("")
    try {
      const res = await fetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ stack: modelStack }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save model stack." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save model stack.")
      } else {
        applyControlsConfig(data)
        await refreshControls()
        setMessages(prev => [...prev, systemMsg("Model stack updated.")])
      }
    } catch {
      setSettingsError("Could not save model stack.")
    } finally {
      setSavingModelStack(false)
    }
  }, [applyControlsConfig, modelStack, refreshControls])

  const saveProviderTokens = useCallback(async () => {
    const payload = Object.fromEntries(
      Object.entries(providerDrafts).filter(([, value]) => value.trim())
    )
    if (!Object.keys(payload).length) {
      setSettingsError("Paste at least one provider token before saving.")
      return
    }
    setSavingProviderTokens(true)
    setSettingsError("")
    try {
      const res = await fetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ providers: payload }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save provider tokens." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save provider tokens.")
      } else {
        applyControlsConfig(data)
        await refreshControls()
        setProviderDrafts({
          openai_api_key: "",
          anthropic_api_key: "",
          google_api_key: "",
          groq_api_key: "",
          minimax_api_key: "",
        })
        setMessages(prev => [...prev, systemMsg("Provider tokens saved.")])
      }
    } catch {
      setSettingsError("Could not save provider tokens.")
    } finally {
      setSavingProviderTokens(false)
    }
  }, [applyControlsConfig, providerDrafts, refreshControls])

  const saveComms = useCallback(async () => {
    setSavingComms(true)
    setSettingsError("")
    try {
      const res = await fetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ comms: commsForm }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save comms settings." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save comms settings.")
      } else {
        applyControlsConfig(data)
        await refreshControls()
        setMessages(prev => [...prev, systemMsg("Communications settings saved. Restart sparkbot-v2 to apply bridge startup changes.")])
      }
    } catch {
      setSettingsError("Could not save comms settings.")
    } finally {
      setSavingComms(false)
    }
  }, [applyControlsConfig, commsForm, refreshControls])

  const saveTokenGuardianMode = useCallback(async () => {
    setSavingTokenGuardianMode(true)
    setSettingsError("")
    try {
      const res = await fetch("/api/v1/chat/models/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ token_guardian_mode: tokenGuardianMode }),
      })
      const data = await res.json().catch(() => ({ detail: "Could not save Token Guardian mode." }))
      if (!res.ok) {
        setSettingsError(data.detail ?? "Could not save Token Guardian mode.")
      } else {
        applyControlsConfig(data)
        await refreshControls()
        setMessages(prev => [...prev, systemMsg(`Token Guardian set to **${tokenGuardianMode}**.`)])
      }
    } catch {
      setSettingsError("Could not save Token Guardian mode.")
    } finally {
      setSavingTokenGuardianMode(false)
    }
  }, [applyControlsConfig, tokenGuardianMode, refreshControls])

  const handleModelStackChange = useCallback((field: keyof ModelStackForm, value: string) => {
    setModelStack(prev => ({ ...prev, [field]: value }))
  }, [])

  const handleProviderDraftChange = useCallback((field: keyof ProviderTokenDrafts, value: string) => {
    setProviderDrafts(prev => ({ ...prev, [field]: value }))
  }, [])

  const handleCommsTextChange = useCallback((section: keyof CommsForm, field: string, value: string) => {
    setCommsForm(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [field]: value,
      },
    }))
  }, [])

  const handleCommsToggleChange = useCallback((section: keyof CommsForm, field: string, value: boolean) => {
    setCommsForm(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [field]: value,
      },
    }))
  }, [])

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

  // ── Voice ────────────────────────────────────────────────────────────────────

  const playTTS = useCallback(async (text: string) => {
    try {
      const res = await fetch("/api/v1/chat/voice/tts", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      })
      if (!res.ok) return
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.onended = () => URL.revokeObjectURL(url)
      audio.play()
    } catch { /* ignore */ }
  }, [])

  const handleVoiceSend = useCallback(async (blob: Blob) => {
    if (!roomId) return
    setSending(true)

    const tempHumanId = `temp-human-${Date.now()}`
    const tempBotId = `temp-bot-${Date.now()}`
    setMessages(prev => [
      ...prev,
      { id: tempHumanId, content: "🎤 …", created_at: new Date().toISOString(), sender_type: "HUMAN" },
      { id: tempBotId, content: "", created_at: new Date().toISOString(), sender_type: "BOT", isStreaming: true },
    ])

    try {
      const form = new FormData()
      form.append("audio", blob, "recording.webm")

      const res = await fetch(`/api/v1/chat/rooms/${roomId}/voice`, {
        method: "POST",
        credentials: "include",
        body: form,
      })

      if (!res.ok || !res.body) {
        setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: "⚠️ Voice send failed.", isStreaming: false } : m))
        setSending(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      let botFullText = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n"); buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.type === "transcription") {
              setMessages(prev => prev.map(m => m.id === tempHumanId ? { ...m, content: ev.text } : m))
            } else if (ev.type === "human_message") {
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
              botFullText += ev.token
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: m.content + ev.token } : m))
            } else if (ev.type === "confirm_required") {
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, content: "", isStreaming: false, toolActivity: undefined } : m))
              setPendingConfirm({ confirmId: ev.confirm_id, tool: ev.tool, input: ev.input ?? {} })
              setSending(false)
              return
            } else if (ev.type === "done") {
              setMessages(prev => prev.map(m => m.id === tempBotId ? { ...m, id: ev.message_id, isStreaming: false, toolActivity: undefined } : m))
              if (voiceMode && botFullText) {
                playTTS(botFullText)
              }
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
  }, [roomId, voiceMode, playTTS])

  const handleVoiceToggle = useCallback(async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop()
      clearInterval(recordingTimerRef.current!)
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" })
      audioChunksRef.current = []
      mr.ondataavailable = e => { if (e.data.size > 0) audioChunksRef.current.push(e.data) }
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        setIsRecording(false)
        setRecordingSeconds(0)
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" })
        await handleVoiceSend(blob)
      }
      mr.start()
      mediaRecorderRef.current = mr
      setIsRecording(true)
      recordingTimerRef.current = setInterval(() => setRecordingSeconds(s => s + 1), 1000)
    } catch { /* mic permission denied — no crash */ }
  }, [isRecording, handleVoiceSend])

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
    const replyId = replyingTo?.id ?? null
    setReplyingTo(null)
    setSending(true)

    const tempHumanId = `temp-human-${Date.now()}`
    const tempBotId = `temp-bot-${Date.now()}`
    setMessages(prev => [
      ...prev,
      { id: tempHumanId, content, created_at: new Date().toISOString(), sender_type: "HUMAN", reply_to_id: replyId ?? undefined },
      { id: tempBotId, content: "", created_at: new Date().toISOString(), sender_type: "BOT", isStreaming: true },
    ])

    try {
      const res = await fetch(`/api/v1/chat/rooms/${roomId}/messages/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ content, ...(replyId ? { reply_to_id: replyId } : {}) }),
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
  }, [inputValue, roomId, sending, handleCommand, captureMeetingItem, agents, replyingTo])

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

  const handleEditSave = useCallback(async (msgId: string) => {
    const trimmed = editContent.trim()
    if (!trimmed || !roomId) { setEditingId(null); return }
    try {
      const res = await fetch(`/api/v1/chat/messages/${roomId}/message/${msgId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ content: trimmed }),
      })
      if (res.ok) {
        setMessages(prev => prev.map(m => m.id === msgId ? { ...m, content: trimmed, is_edited: true } : m))
      }
    } catch { /* ignore — message stays as-is */ }
    setEditingId(null)
  }, [roomId, editContent])

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
        dashboardSummary={controlsDashboard}
        modelsConfig={modelsConfig}
        modelStack={modelStack}
        providerDrafts={providerDrafts}
        commsForm={commsForm}
        savingModelStack={savingModelStack}
        savingProviderTokens={savingProviderTokens}
        savingComms={savingComms}
        tokenGuardianMode={tokenGuardianMode}
        savingTokenGuardianMode={savingTokenGuardianMode}
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
        onModelStackChange={handleModelStackChange}
        onProviderDraftChange={handleProviderDraftChange}
        onCommsTextChange={handleCommsTextChange}
        onCommsToggleChange={handleCommsToggleChange}
        onSaveModelStack={saveModelStack}
        onSaveProviderTokens={saveProviderTokens}
        onSaveComms={saveComms}
        onTokenGuardianModeChange={setTokenGuardianMode}
        onSaveTokenGuardianMode={saveTokenGuardianMode}
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
            const parentMsg = msg.reply_to_id ? messages.find(m => m.id === msg.reply_to_id) : null
            const isEditing = editingId === msg.id
            return (
              <div key={msg.id} className={`group flex ${own ? "justify-end" : "justify-start"}`}>
                <div className="flex flex-col max-w-[75%]">
                  {/* Reply quote */}
                  {parentMsg && (
                    <div className={`mb-1 px-3 py-1 rounded-lg border-l-2 border-primary/50 bg-muted/40 text-[11px] text-muted-foreground truncate ${own ? "self-end" : "self-start"}`}>
                      ↩ {parentMsg.sender_type === "BOT" ? "Sparkbot" : (parentMsg.sender_username ?? "You")}: {parentMsg.content.slice(0, 80)}{parentMsg.content.length > 80 ? "…" : ""}
                    </div>
                  )}
                  <div className={`flex items-end gap-1 ${own ? "flex-row-reverse" : "flex-row"}`}>
                    <div className={`rounded-2xl px-4 py-2 ${own ? "rounded-br-md bg-primary text-primary-foreground" : "rounded-bl-md bg-muted"}`}>
                      {isEditing ? (
                        <div className="flex flex-col gap-1">
                          <textarea
                            autoFocus
                            value={editContent}
                            onChange={e => setEditContent(e.target.value)}
                            onKeyDown={e => {
                              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleEditSave(msg.id) }
                              if (e.key === "Escape") setEditingId(null)
                            }}
                            className="text-sm w-full rounded bg-background/20 px-2 py-1 outline-none resize-none min-w-[180px]"
                            rows={Math.min(6, editContent.split("\n").length + 1)}
                          />
                          <div className="flex gap-2 justify-end text-[11px]">
                            <button onClick={() => setEditingId(null)} className="opacity-70 hover:opacity-100">Cancel</button>
                            <button onClick={() => handleEditSave(msg.id)} className="font-medium hover:opacity-80">Save</button>
                          </div>
                        </div>
                      ) : isBot(msg)
                        ? <BotMessage content={msg.content} isStreaming={msg.isStreaming} toolActivity={msg.toolActivity} agent={msg.agent} />
                        : <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>
                      }
                      <p className={`text-[10px] mt-1 opacity-70 ${own ? "text-right" : ""}`}>
                        {new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        {msg.isStreaming && " · typing…"}
                        {msg.is_edited && " · edited"}
                      </p>
                    </div>
                    {/* Hover action buttons */}
                    {!isEditing && !msg.isStreaming && (
                      <div className={`flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity mb-1 ${own ? "flex-row-reverse" : "flex-row"}`}>
                        <button
                          onClick={() => setReplyingTo(msg)}
                          title="Reply"
                          className="flex h-6 w-6 items-center justify-center rounded-full hover:bg-muted text-muted-foreground"
                        >
                          <CornerUpLeft className="h-3.5 w-3.5" />
                        </button>
                        {own && (
                          <button
                            onClick={() => { setEditingId(msg.id); setEditContent(msg.content) }}
                            title="Edit"
                            className="flex h-6 w-6 items-center justify-center rounded-full hover:bg-muted text-muted-foreground"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t px-4 py-3 shrink-0">
        {/* Reply banner */}
        {replyingTo && (
          <div className="flex items-center justify-between mb-2 px-3 py-1.5 rounded-lg bg-muted/50 text-[11px] text-muted-foreground">
            <span className="truncate">
              <CornerUpLeft className="inline h-3 w-3 mr-1 align-middle" />
              Replying to{" "}
              <span className="font-medium">{replyingTo.sender_type === "BOT" ? "Sparkbot" : (replyingTo.sender_username ?? "you")}</span>
              {": "}
              {replyingTo.content.slice(0, 80)}{replyingTo.content.length > 80 ? "…" : ""}
            </span>
            <button onClick={() => setReplyingTo(null)} className="ml-2 shrink-0 hover:text-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
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

          {/* Mic button */}
          <button
            onClick={handleVoiceToggle}
            disabled={sending || uploading}
            title={isRecording ? `Recording ${recordingSeconds}s — click to send` : "Voice message"}
            className={`flex h-9 w-9 items-center justify-center rounded-full disabled:opacity-40 ${
              isRecording ? "bg-red-500 text-white animate-pulse" : "text-muted-foreground hover:bg-muted"
            }`}
          >
            {isRecording
              ? <span className="text-[10px] font-mono">{recordingSeconds}s</span>
              : <Mic className="h-4 w-4" />}
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

          {/* Voice mode toggle */}
          <button
            onClick={() => {
              const next = !voiceMode
              setVoiceMode(next)
              localStorage.setItem("sparkbot_voice_mode", String(next))
            }}
            title={voiceMode ? "Voice mode on — replies spoken aloud" : "Voice mode off"}
            className={`flex h-9 w-9 items-center justify-center rounded-full ${
              voiceMode ? "text-primary" : "text-muted-foreground hover:bg-muted"
            }`}
          >
            {voiceMode ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}

export default SparkbotDmPage
