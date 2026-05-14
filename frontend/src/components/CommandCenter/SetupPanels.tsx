// SetupPanels — extracted controls UI for inline rendering in Command Center

import { useState, useEffect, useMemo } from "react"
import { ChevronDown, RefreshCw } from "lucide-react"
import type {
  ModelsControlsConfig,
  ModelStackForm,
  ProviderTokenDrafts,
  DefaultModelSelectionForm,
  AgentRoutingOverride,
  OpenRouterModelRecord,
  CommsForm,
  OllamaStatus,
  GuardianStatus,
  ControlsDashboardSummary,
  GuardianTaskRecord,
  GuardianRunRecord,
  SkillInfo,
  PolicyEntry,
  Agent,
} from "@/hooks/useControlsState"
import { AGENT_TEMPLATES } from "@/hooks/useControlsState"

// ─── Shared helpers ──────────────────────────────────────────────────────────

function agentDisplayName(name: string): string {
  if (name === "sparkbot") return "Sparkbot"
  return name.split("_").filter(Boolean).map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(" ")
}

// ─── Shared props type for all panels ────────────────────────────────────────

export interface SetupPanelProps {
  modelsConfig: ModelsControlsConfig | null
  modelStack: ModelStackForm
  defaultSelection: DefaultModelSelectionForm
  localDefaultModel: string
  agentOverrides: Record<string, AgentRoutingOverride>
  openRouterModels: OpenRouterModelRecord[]
  providerDrafts: ProviderTokenDrafts
  commsForm: CommsForm
  commsOpenSection: string | null
  ollamaStatus: OllamaStatus | null
  ollamaBaseUrl: string
  ollamaLoading: boolean
  guardianStatus: GuardianStatus | null
  controlsDashboard: ControlsDashboardSummary | null
  guardianTasks: GuardianTaskRecord[]
  guardianRuns: GuardianRunRecord[]
  skills: SkillInfo[]
  policyEntries: PolicyEntry[]
  agents: Agent[]
  error: string
  // Token Guardian
  tokenGuardianMode: string
  savingTokenGuardianMode: boolean
  // Saving flags
  savingModelStack: boolean
  savingProviderTokens: boolean
  savingDefaultSelection: boolean
  savingAgentOverrides: boolean
  savingComms: boolean
  loadingOpenRouterModels: boolean
  openRouterLoadError: string
  // Execution / PIN
  savingExecution: boolean
  executionSaved: boolean
  executionError: string
  customGuardrails: string
  savingPin: boolean
  pinSaved: boolean
  pinError: string
  // Task Guardian
  taskName: string
  taskToolName: string
  taskSchedule: string
  taskArgs: string
  taskSaving: boolean
  // Persona
  roomPersona: string
  savingPersona: boolean
  personaSaved: boolean
  // Spawn
  spawnTemplate: string
  spawnName: string
  spawnEmoji: string
  spawnDescription: string
  spawnPrompt: string
  spawning: boolean
  // Callbacks
  onRefresh: () => void
  onDefaultSelectionChange: (field: keyof DefaultModelSelectionForm, value: string) => void
  onLocalDefaultModelChange: (value: string) => void
  onProviderDraftChange: (field: keyof ProviderTokenDrafts, value: string) => void
  onModelStackChange: (field: keyof ModelStackForm, value: string) => void
  onAgentOverrideChange: (agentName: string, field: keyof AgentRoutingOverride, value: string) => void
  onCommsTextChange: (section: keyof CommsForm, field: string, value: string) => void
  onCommsToggleChange: (section: keyof CommsForm, field: string, value: boolean) => void
  onCommsOpenSectionChange: (section: string | null) => void
  onSaveModelStack: () => void
  onSaveProviderTokens: () => void
  onSaveDefaultSelection: () => void
  onSaveAgentOverrides: () => void
  onLoadOpenRouterModels: () => void
  onSaveComms: () => void
  onTokenGuardianModeChange: (value: string) => void
  onSaveTokenGuardianMode: () => void
  onToggleExecution: (enabled: boolean) => void
  onCustomGuardrailsChange: (value: string) => void
  onSaveCustomGuardrails: () => void
  onSavePin: (currentPin: string, pin: string, pinConfirm: string) => void
  onOllamaBaseUrlChange: (url: string) => void
  onCheckOllamaStatus: () => void
  onTaskNameChange: (value: string) => void
  onTaskToolChange: (value: string) => void
  onTaskScheduleChange: (value: string) => void
  onTaskArgsChange: (value: string) => void
  onCreateTask: () => void
  onToggleTask: (taskId: string, enabled: boolean) => void
  onRunTask: (taskId: string) => void
  onPersonaChange: (value: string) => void
  onSavePersona: () => void
  onSpawnTemplateChange: (id: string) => void
  onSpawnNameChange: (v: string) => void
  onSpawnEmojiChange: (v: string) => void
  onSpawnDescriptionChange: (v: string) => void
  onSpawnPromptChange: (v: string) => void
  onSpawnAgent: () => void
}

// ─── Derived helpers (used inside panels) ────────────────────────────────────

function useSetupHelpers(props: SetupPanelProps) {
  const { modelsConfig, openRouterModels, localDefaultModel, ollamaStatus, modelStack, commsForm, guardianStatus } = props

  const localModelOptions = useMemo(() => Array.from(
    new Set([
      localDefaultModel,
      ...(ollamaStatus?.models ?? []).map((m) => m.startsWith("ollama/") ? m : `ollama/${m}`),
    ].filter(Boolean)),
  ), [localDefaultModel, ollamaStatus])

  const stackModelOptions = useMemo(() => Array.from(
    new Set([
      ...Object.keys(modelsConfig?.model_labels ?? {}),
      ...openRouterModels.map((m) => m.id),
      ...localModelOptions,
      modelStack?.primary, modelStack?.backup_1, modelStack?.backup_2, modelStack?.heavy_hitter,
    ].filter(Boolean)),
  ), [modelsConfig, openRouterModels, localModelOptions, modelStack])

  const modelOptionLabel = (modelId: string) =>
    modelsConfig?.model_labels?.[modelId]
    ?? openRouterModels.find((m) => m.id === modelId)?.label
    ?? modelId.replace("ollama/", "")

  const providerOrder: Array<[string, string, (id: string) => boolean]> = [
    ["openrouter", "OpenRouter (OPENROUTER_API_KEY)", (id) => id.startsWith("openrouter/")],
    ["openai", "OpenAI direct (OPENAI_API_KEY)", (id) => id.startsWith("gpt-") || id.startsWith("codex-")],
    ["openai_codex", "OpenAI Codex subscription", (id) => id.startsWith("openai-codex/")],
    ["anthropic", "Anthropic direct (ANTHROPIC_API_KEY)", (id) => id.startsWith("claude")],
    ["google", "Google direct (GOOGLE_API_KEY)", (id) => id.startsWith("gemini/")],
    ["xai", "xAI direct (XAI_API_KEY)", (id) => id.startsWith("xai/")],
    ["groq", "Groq direct (GROQ_API_KEY)", (id) => id.startsWith("groq/")],
    ["minimax", "MiniMax direct (MINIMAX_API_KEY)", (id) => id.startsWith("minimax/")],
    ["ollama", "Local (Ollama — no API key)", (id) => id.startsWith("ollama/")],
  ]
  const stackModelGroups = providerOrder
    .map(([, label, test]) => ({ label, models: stackModelOptions.filter(test) }))
    .filter((g) => g.models.length > 0)

  const hasOpenRouterConfigured = Boolean(modelsConfig?.providers?.find((p) => p.id === "openrouter")?.configured)
  const directProviderLabel: Record<string, string> = {
    openai: "OpenAI", openai_codex: "OpenAI Codex Subscription", anthropic: "Anthropic",
    google: "Google", groq: "Groq", minimax: "MiniMax", xai: "xAI",
  }
  const directProviderKeyField: Record<string, keyof ProviderTokenDrafts> = {
    openai: "openai_api_key", anthropic: "anthropic_api_key",
    google: "google_api_key", groq: "groq_api_key", minimax: "minimax_api_key", xai: "xai_api_key",
  }
  const directProviderAuthModes = (id: string): string[] =>
    modelsConfig?.providers?.find((p) => p.id === id)?.auth_modes ?? ["api_key"]
  const directProviderIsConfigured = (id: string) =>
    Boolean(modelsConfig?.providers?.find((p) => p.id === id)?.configured)
  const directProviderModels = (id: string): string[] =>
    modelsConfig?.providers?.find((p) => p.id === id)?.models ?? []
  const ollamaProvider = modelsConfig?.providers?.find((p) => p.id === "ollama")
  const routingAgents = modelsConfig?.available_agents ?? []
  const pinConfigured = Boolean(guardianStatus?.pin_configured)
  const securityGuardrailsActive = Boolean(modelsConfig?.security_guardrails_enabled ?? guardianStatus?.security_guardrails_enabled)
  const readyProviderCount = modelsConfig?.providers?.filter(
    (p) => p.configured || p.models_available === true,
  ).length ?? 0
  const enabledChannelCount = [
    Boolean(commsForm.telegram.enabled && modelsConfig?.comms?.telegram?.configured),
    Boolean(commsForm.discord.enabled && modelsConfig?.comms?.discord?.configured),
    Boolean(commsForm.whatsapp.enabled && modelsConfig?.comms?.whatsapp?.configured),
    Boolean(commsForm.github.enabled && modelsConfig?.comms?.github?.configured),
    Boolean(modelsConfig?.comms?.google?.gmail_configured),
    Boolean(modelsConfig?.comms?.google?.calendar_configured),
    Boolean(modelsConfig?.comms?.google?.drive_configured),
    Boolean(modelsConfig?.comms?.microsoft?.configured),
  ].filter(Boolean).length

  return {
    localModelOptions, stackModelGroups, modelOptionLabel, hasOpenRouterConfigured,
    directProviderLabel, directProviderKeyField, directProviderAuthModes,
    directProviderIsConfigured, directProviderModels, ollamaProvider, routingAgents,
    pinConfigured, securityGuardrailsActive,
    readyProviderCount, enabledChannelCount,
  }
}

// ─── Collapsible section wrapper ─────────────────────────────────────────────

function CollapsibleSection({ title, subtitle, defaultOpen = false, children }: {
  title: string
  subtitle?: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-xl border border-blue-500/20 bg-card">
      <button
        type="button"
        className="flex w-full items-center justify-between px-5 py-4 text-left"
        onClick={() => setOpen(!open)}
      >
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="border-t border-blue-500/10 px-5 pb-5 pt-4">{children}</div>}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// AI SETUP PANEL
// ═══════════════════════════════════════════════════════════════════════════════

export function AISetupPanel(props: SetupPanelProps) {
  const {
    modelsConfig, defaultSelection, modelStack, providerDrafts,
    openRouterModels, loadingOpenRouterModels, openRouterLoadError,
    ollamaStatus, ollamaBaseUrl, ollamaLoading, error,
    savingModelStack, savingProviderTokens, savingDefaultSelection,
    onDefaultSelectionChange, onLocalDefaultModelChange, onProviderDraftChange,
    onModelStackChange, onSaveModelStack, onSaveProviderTokens,
    onSaveDefaultSelection, onLoadOpenRouterModels, onOllamaBaseUrlChange,
    onCheckOllamaStatus,
  } = props

  const {
    localModelOptions, stackModelGroups, modelOptionLabel,
    hasOpenRouterConfigured, directProviderLabel, directProviderKeyField,
    directProviderAuthModes, directProviderIsConfigured, directProviderModels,
    ollamaProvider,
  } = useSetupHelpers(props)

  return (
    <CollapsibleSection title="AI Setup" subtitle="Provider selection, model picker, local AI, four-model stack" defaultOpen>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            Choose your default AI provider. OpenRouter is the easiest all-in-one cloud path.
          </p>
          <button
            type="button"
            onClick={onLoadOpenRouterModels}
            disabled={loadingOpenRouterModels}
            className="shrink-0 rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50"
          >
            {loadingOpenRouterModels ? "Refreshing..." : "Refresh models"}
          </button>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-4">
            {/* Provider pills */}
            <div className="rounded-lg border bg-muted/30 p-4">
              <div className="mb-3 flex flex-wrap gap-2">
                {([
                  ["openrouter", "OpenRouter"], ["openai", "OpenAI"], ["openai_codex", "Codex Sub"],
                  ["anthropic", "Anthropic"], ["claude_sub", "Claude Sub"], ["google", "Google"],
                  ["groq", "Groq"], ["minimax", "MiniMax"], ["xai", "xAI"], ["ollama", "Local (Ollama)"],
                ] as [string, string][]).map(([providerId, label]) => (
                  <button
                    key={providerId}
                    type="button"
                    onClick={() => onDefaultSelectionChange("provider", providerId)}
                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                      defaultSelection.provider === providerId
                        ? "border-blue-500 bg-blue-600 text-white"
                        : "border-border bg-background hover:bg-muted"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {/* Provider-specific config */}
              {defaultSelection.provider === "openrouter" ? (
                <div className="space-y-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">OpenRouter API key</label>
                    <input
                      type="password"
                      value={providerDrafts.openrouter_api_key}
                      onChange={(e) => onProviderDraftChange("openrouter_api_key", e.target.value)}
                      onBlur={() => { if (providerDrafts.openrouter_api_key.trim().length > 3) onLoadOpenRouterModels() }}
                      placeholder={hasOpenRouterConfigured ? "Saved already. Paste new key only to replace." : "Paste OpenRouter API key"}
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">
                      Default cloud model
                      {openRouterModels.length > 0 && (
                        <span className="ml-2 text-muted-foreground/60">
                          ({openRouterModels.filter(m => m.is_free).length} free, {openRouterModels.filter(m => !m.is_free).length} paid)
                        </span>
                      )}
                    </label>
                    <select
                      value={defaultSelection.provider === "openrouter" ? defaultSelection.model : ""}
                      onChange={(e) => onDefaultSelectionChange("model", e.target.value)}
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                    >
                      <option value="">{openRouterModels.length === 0 ? "Click \"Refresh models\" to load" : "Choose an OpenRouter model"}</option>
                      {openRouterModels.filter(m => m.is_free).length > 0 && (
                        <optgroup label={`Free models (${openRouterModels.filter(m => m.is_free).length})`}>
                          {openRouterModels.filter(m => m.is_free).map((m) => (<option key={m.id} value={m.id}>{m.label}</option>))}
                        </optgroup>
                      )}
                      {openRouterModels.filter(m => !m.is_free).length > 0 && (
                        <optgroup label={`Paid models (${openRouterModels.filter(m => !m.is_free).length})`}>
                          {openRouterModels.filter(m => !m.is_free).map((m) => (<option key={m.id} value={m.id}>{m.label}</option>))}
                        </optgroup>
                      )}
                    </select>
                    {openRouterLoadError && <p className="mt-1 text-xs font-medium text-destructive">{openRouterLoadError}</p>}
                  </div>
                </div>
              ) : defaultSelection.provider === "openai_codex" ? (
                <div className="space-y-3">
                  <div className="rounded-md border bg-background px-3 py-2">
                    <div className="text-xs font-semibold">
                      {directProviderIsConfigured("openai_codex") ? "Codex ChatGPT sign-in detected" : "Codex ChatGPT sign-in needed"}
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Run <code className="rounded bg-muted px-1 py-0.5">codex login</code>, choose ChatGPT sign-in, then restart Sparkbot.
                    </p>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">Default Codex model</label>
                    <select
                      value={defaultSelection.model}
                      onChange={(e) => onDefaultSelectionChange("model", e.target.value)}
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                    >
                      <option value="">Choose a Codex subscription model</option>
                      {directProviderModels("openai_codex").map((m) => (
                        <option key={m} value={m}>{modelsConfig?.model_labels?.[m] ?? m}</option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : defaultSelection.provider === "claude_sub" ? (
                <div className="space-y-3">
                  <div className="rounded-md border bg-background px-3 py-2">
                    <div className="text-xs font-semibold">
                      {directProviderIsConfigured("claude_sub") ? "Claude Code sign-in detected" : "Claude Code sign-in needed"}
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Run <code className="rounded bg-muted px-1 py-0.5">claude auth login</code>, then restart Sparkbot.
                    </p>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">Default Claude model</label>
                    <select
                      value={defaultSelection.model}
                      onChange={(e) => onDefaultSelectionChange("model", e.target.value)}
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                    >
                      <option value="">Choose a Claude subscription model</option>
                      {directProviderModels("claude_sub").map((m) => (
                        <option key={m} value={m}>{modelsConfig?.model_labels?.[m] ?? m}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex justify-end">
                    <button type="button" onClick={onSaveDefaultSelection} disabled={savingDefaultSelection}
                      className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50">
                      {savingDefaultSelection ? "Saving..." : "Save"}
                    </button>
                  </div>
                </div>
              ) : defaultSelection.provider === "ollama" ? (
                <div className="space-y-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">Default local model</label>
                    <select
                      value={defaultSelection.provider === "ollama" ? defaultSelection.model : ""}
                      onChange={(e) => { onLocalDefaultModelChange(e.target.value); onDefaultSelectionChange("model", e.target.value) }}
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                    >
                      <option value="">Choose a downloaded Ollama model</option>
                      {localModelOptions.map((m) => (
                        <option key={m} value={m}>{modelsConfig?.model_labels?.[m] ?? m.replace("ollama/", "")}</option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : directProviderKeyField[defaultSelection.provider] !== undefined ? (
                <div className="space-y-3">
                  {directProviderAuthModes(defaultSelection.provider).length > 1 && (
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">Credential mode</label>
                      <div className="flex gap-2">
                        {directProviderAuthModes(defaultSelection.provider).map((mode) => {
                          const authField = defaultSelection.provider === "openai" ? "openai_auth_mode" : "anthropic_auth_mode"
                          const active = providerDrafts[authField] === mode
                          return (
                            <button key={mode} type="button" onClick={() => onProviderDraftChange(authField, mode)}
                              className={`flex-1 rounded-md border px-3 py-2 text-xs font-semibold transition-colors ${
                                active ? "border-blue-500 bg-blue-600 text-white" : "border-border bg-background hover:bg-muted"
                              }`}>
                              {mode === "api_key" ? "API Key" : "Subscription"}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">
                      {`${directProviderLabel[defaultSelection.provider]} API key`}
                    </label>
                    <input
                      type="password"
                      value={providerDrafts[directProviderKeyField[defaultSelection.provider]]}
                      onChange={(e) => onProviderDraftChange(directProviderKeyField[defaultSelection.provider], e.target.value)}
                      placeholder={directProviderIsConfigured(defaultSelection.provider)
                        ? "Saved. Paste a new key only if replacing."
                        : `Paste ${directProviderLabel[defaultSelection.provider]} API key`}
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                    />
                    {directProviderIsConfigured(defaultSelection.provider) && (
                      <p className="mt-1 text-[11px] text-blue-600">Key saved and active.</p>
                    )}
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">Default model</label>
                    <select
                      value={defaultSelection.model}
                      onChange={(e) => onDefaultSelectionChange("model", e.target.value)}
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none"
                    >
                      <option value="">Choose a {directProviderLabel[defaultSelection.provider]} model</option>
                      {directProviderModels(defaultSelection.provider).map((m) => (
                        <option key={m} value={m}>{modelsConfig?.model_labels?.[m] ?? m}</option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : null}

              {error && <p className="mt-2 text-xs font-medium text-destructive">{error}</p>}
              <div className="mt-4 flex justify-end gap-2">
                {(defaultSelection.provider === "openrouter" || directProviderKeyField[defaultSelection.provider] !== undefined) ? (
                  <button type="button" onClick={onSaveProviderTokens} disabled={savingProviderTokens}
                    className="rounded-md border px-4 py-2 text-sm hover:bg-muted disabled:opacity-50">
                    {savingProviderTokens ? "Saving key..." : `Save ${directProviderLabel[defaultSelection.provider] ?? "OpenRouter"} credential`}
                  </button>
                ) : null}
                <button type="button" onClick={onSaveDefaultSelection} disabled={savingDefaultSelection}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50">
                  {savingDefaultSelection ? "Saving default..." : "Save default model"}
                </button>
              </div>
            </div>

            {/* Local AI */}
            <div className="rounded-lg border bg-muted/20 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold">Local AI on this machine</h3>
                  <p className="text-xs text-muted-foreground">Keep local models visible even when OpenRouter is your default.</p>
                </div>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${ollamaStatus?.reachable ? "bg-blue-500/15 text-blue-600" : "bg-muted text-muted-foreground"}`}>
                  {ollamaStatus === null ? "Unknown" : ollamaStatus.reachable ? "Running" : "Not found"}
                </span>
              </div>
              <div className="mb-3 flex items-center gap-2">
                <input type="text" value={ollamaBaseUrl} onChange={(e) => onOllamaBaseUrlChange(e.target.value)}
                  placeholder="http://localhost:11434" className="flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none" />
                <button type="button" onClick={onCheckOllamaStatus} disabled={ollamaLoading}
                  className="rounded-md border px-3 py-2 text-xs font-medium hover:bg-muted disabled:opacity-50">
                  {ollamaLoading ? "Checking..." : "Refresh"}
                </button>
              </div>
              <div className="mb-3 flex flex-wrap gap-1.5">
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${ollamaProvider?.configured ? "bg-blue-500/15 text-blue-700 dark:text-blue-400" : "bg-muted text-muted-foreground"}`}>
                  {ollamaProvider?.configured ? "Saved for local routing" : "No saved local route yet"}
                </span>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${ollamaStatus?.reachable ? "bg-blue-500/15 text-blue-600" : "bg-muted text-muted-foreground"}`}>
                  {ollamaStatus?.reachable ? "Runtime reachable" : "Runtime not reachable"}
                </span>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${ollamaStatus?.models_available ? "bg-blue-500/15 text-blue-600" : "bg-muted text-muted-foreground"}`}>
                  {ollamaStatus?.models_available ? "Local model downloaded" : "No downloaded model yet"}
                </span>
              </div>
              {ollamaStatus?.reachable ? (
                <>
                  <div className="mb-3">
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">Preferred local model</label>
                    <select value={localModelOptions.includes(props.localDefaultModel) ? props.localDefaultModel : ""}
                      onChange={(e) => onLocalDefaultModelChange(e.target.value)}
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none">
                      <option value="">Choose a local model</option>
                      {localModelOptions.map((m) => (
                        <option key={m} value={m}>{modelsConfig?.model_labels?.[m] ?? m.replace("ollama/", "")}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[10px] text-muted-foreground">Downloaded:</span>
                    {(ollamaStatus?.models?.length ?? 0) > 0 ? (ollamaStatus?.models ?? []).map((m) => (
                      <span key={m} className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-700 dark:text-blue-400">{m}</span>
                    )) : <span className="text-xs text-muted-foreground">No local models downloaded yet.</span>}
                  </div>
                </>
              ) : (
                <div className="rounded-md border border-amber-500/30 bg-amber-50/20 dark:bg-amber-950/20 px-3 py-3">
                  <p className="text-xs font-medium text-amber-700 dark:text-amber-400">Ollama not detected at {ollamaBaseUrl}</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Install Ollama from <span className="font-mono">ollama.com</span>, then run <code className="rounded bg-muted px-1 py-0.5">ollama run phi4-mini</code>.
                  </p>
                </div>
              )}
            </div>

            {/* Four-model stack */}
            <div className="rounded-lg border bg-muted/20 p-4">
              <div className="mb-3">
                <h3 className="text-sm font-semibold">Four-model stack</h3>
                <p className="text-xs text-muted-foreground">Token Guardian routes between these models. Primary is your active chat model.</p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {([
                  ["primary", "Primary (= active model)"],
                  ["backup_1", "Backup 1"],
                  ["backup_2", "Backup 2"],
                  ["heavy_hitter", "Heavy hitter (complex tasks)"],
                ] as const).map(([field, label]) => (
                  <div key={field}>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">{label}</label>
                    <select value={modelStack[field]}
                      onChange={(e) => onModelStackChange(field, e.target.value)}
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none">
                      <option value="">Choose a model</option>
                      {stackModelGroups.map((group) => (
                        <optgroup key={group.label} label={group.label}>
                          {group.models.map((modelId) => (
                            <option key={`${field}-${modelId}`} value={modelId}>{modelOptionLabel(modelId)}</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex justify-end">
                <button type="button" onClick={onSaveModelStack} disabled={savingModelStack}
                  className="rounded-md border px-4 py-2 text-sm hover:bg-muted disabled:opacity-50">
                  {savingModelStack ? "Saving stack..." : "Save stack"}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Current default */}
        <div className="rounded-lg border bg-background/60 px-3 py-3">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Current default</div>
          <div className="mt-2 text-xs text-muted-foreground">
            {modelsConfig?.default_selection?.label ?? modelsConfig?.default_selection?.model ?? "No default selected"}
          </div>
        </div>
      </div>
    </CollapsibleSection>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// PIN & SECURITY PANEL
// ═══════════════════════════════════════════════════════════════════════════════

export function PinSecurityPanel(props: SetupPanelProps) {
  const {
    guardianStatus,
    customGuardrails,
    savingExecution, executionSaved, executionError,
    savingPin, pinSaved, pinError,
    onToggleExecution, onCustomGuardrailsChange, onSaveCustomGuardrails, onSavePin, onRefresh,
  } = props

  const { pinConfigured, securityGuardrailsActive } = useSetupHelpers(props)

  const [currentPinDraft, setCurrentPinDraft] = useState("")
  const [pinDraft, setPinDraft] = useState("")
  const [pinConfirmDraft, setPinConfirmDraft] = useState("")
  const pinReady = /^\d{6}$/.test(pinDraft) && pinDraft === pinConfirmDraft && (!pinConfigured || currentPinDraft.length > 0)

  useEffect(() => {
    if (!pinSaved) return
    setCurrentPinDraft(""); setPinDraft(""); setPinConfirmDraft("")
  }, [pinSaved])

  return (
    <div className="rounded-xl border border-blue-500/20 bg-card p-5 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Security</h2>
          <p className="text-xs text-muted-foreground">Owner-enabled guardrails, custom blockers, and operator PIN management</p>
        </div>
        <button onClick={onRefresh} className="rounded border px-1.5 py-0.5 text-[10px] hover:bg-muted" type="button">
          <span className="inline-flex items-center gap-1"><RefreshCw className="size-3" /> Refresh</span>
        </button>
      </div>

      {/* Security guardrails toggle */}
      <div className={`rounded-lg border px-3 py-3 ${securityGuardrailsActive ? "border-blue-500/30 bg-blue-500/10" : "border-muted bg-muted/20"}`}>
        <div className="flex items-center justify-between gap-3">
          <label className="flex min-w-0 items-start gap-3">
            <input
              type="checkbox"
              checked={securityGuardrailsActive}
              disabled={savingExecution}
              onChange={(event) => onToggleExecution(event.target.checked)}
              className="mt-0.5 h-4 w-4"
            />
            <div>
              <div className="text-xs font-semibold">Security {securityGuardrailsActive ? "ON" : "OFF"}</div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                {securityGuardrailsActive
                  ? "Strict Security guardrails, PIN prompts, service allowlists, and custom blockers are active."
                  : "Default owner mode: routine actions run; writes, deletes, sends, and service changes still ask yes/no."}
              </div>
            </div>
          </label>
          <button type="button" disabled={savingExecution} onClick={() => onToggleExecution(!securityGuardrailsActive)}
            className={`min-w-24 rounded-md border px-3 py-2 text-xs font-semibold transition-colors ${
              securityGuardrailsActive
                ? "border-blue-500/40 bg-blue-600 text-white"
                : "border-muted bg-background hover:bg-muted"
            }`}>
            {savingExecution ? "Saving..." : securityGuardrailsActive ? "Turn Off" : "Turn On"}
          </button>
        </div>
        {executionSaved && <p className="mt-1 text-[10px] font-medium text-blue-600">Saved.</p>}
        {executionError && <p className="mt-1 text-[10px] font-medium text-destructive">{executionError}</p>}
      </div>

      {/* Custom guardrails */}
      <div className="rounded-md border bg-muted/20 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Custom blockers
          </span>
          <span className="text-[10px] text-muted-foreground">{customGuardrails.length}/4000</span>
        </div>
        <textarea
          className="mt-2 h-28 w-full resize-none rounded border bg-background px-2 py-1.5 font-mono text-xs"
          value={customGuardrails}
          onChange={(event) => onCustomGuardrailsChange(event.target.value.slice(0, 4000))}
          placeholder={"One rule per line. Examples:\ntool:gmail_send\nregex:rm\\s+-rf\nkalshi-live-trading"}
        />
        <div className="mt-2 flex justify-end">
          <button type="button"
            className="rounded-md border px-2 py-1 text-[10px] font-medium hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
            disabled={savingExecution}
            onClick={onSaveCustomGuardrails}>
            {savingExecution ? "Saving..." : "Save guardrails"}
          </button>
        </div>
        <p className="mt-1 text-[10px] text-muted-foreground">
          Rules apply when Security is on. Use plain text, tool:name, or regex:pattern.
        </p>
      </div>

      {/* PIN management */}
      <div className="rounded-md border bg-muted/30 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            {pinConfigured ? "Change PIN" : "Set 6-digit PIN"}
          </span>
          <span className={`text-[10px] font-medium ${pinConfigured ? "text-blue-600" : "text-amber-600"}`}>
            {pinConfigured ? "Configured" : "Required"}
          </span>
        </div>
        {pinConfigured && (
          <input className="mt-2 w-full rounded border bg-background px-2 py-1.5 text-xs" type="password"
            inputMode="numeric" maxLength={6} placeholder="Current PIN" value={currentPinDraft}
            onChange={(e) => setCurrentPinDraft(e.target.value.replace(/\D/g, "").slice(0, 6))} />
        )}
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <input className="w-full rounded border bg-background px-2 py-1.5 text-xs" type="password"
            inputMode="numeric" maxLength={6} placeholder={pinConfigured ? "New PIN" : "New 6-digit PIN"}
            value={pinDraft} onChange={(e) => setPinDraft(e.target.value.replace(/\D/g, "").slice(0, 6))} />
          <input className="w-full rounded border bg-background px-2 py-1.5 text-xs" type="password"
            inputMode="numeric" maxLength={6} placeholder="Verify PIN" value={pinConfirmDraft}
            onChange={(e) => setPinConfirmDraft(e.target.value.replace(/\D/g, "").slice(0, 6))} />
        </div>
        <button type="button"
          className="mt-2 rounded-md border px-2 py-1 text-[10px] font-medium hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!pinReady || savingPin} onClick={() => onSavePin(currentPinDraft, pinDraft, pinConfirmDraft)}>
          {savingPin ? "Saving..." : pinConfigured ? "Change PIN" : "Save PIN"}
        </button>
        {pinSaved && <p className="mt-1 text-[10px] font-medium text-blue-600">PIN saved.</p>}
        {pinError && <p className="mt-1 text-[10px] font-medium text-destructive">{pinError}</p>}
      </div>

      {/* Break-glass status */}
      {guardianStatus && (
        <div className="rounded-md border bg-muted/20 px-3 py-2 text-[10px] text-muted-foreground space-y-1">
          <div>Break-glass: {guardianStatus.breakglass.active ? <span className="text-amber-600 font-semibold">ACTIVE</span> : "Inactive"}</div>
          <div>Vault: {guardianStatus.vault_configured ? "Configured" : "Not configured"}</div>
          <div>Memory Guardian: {guardianStatus.memory_guardian_enabled ? "On" : "Off"}</div>
          <div>Task Guardian: {guardianStatus.task_guardian_enabled ? "On" : "Off"}</div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMMS SETUP PANEL
// ═══════════════════════════════════════════════════════════════════════════════

export function CommsSetupPanel(props: SetupPanelProps) {
  const {
    modelsConfig, commsForm, commsOpenSection, savingComms,
    onCommsTextChange, onCommsToggleChange, onCommsOpenSectionChange, onSaveComms,
  } = props

  const LEGACY_COMMS_VISIBLE = true

  function CommsAccordionItem({ id, label, configured, detail, children }: {
    id: string; label: string; configured: boolean; detail?: string; children: React.ReactNode
  }) {
    return (
      <div>
        <button type="button"
          className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-muted/40"
          onClick={() => onCommsOpenSectionChange(commsOpenSection === id ? null : id)}>
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium">{label}</span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${configured ? "bg-blue-500/15 text-blue-600" : "bg-muted text-muted-foreground"}`}>
              {configured ? "Configured" : "Missing"}
            </span>
            {detail && <span className="text-[10px] text-muted-foreground/60">{detail}</span>}
          </div>
          <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${commsOpenSection === id ? "rotate-180" : ""}`} />
        </button>
        {commsOpenSection === id && <div className="border-t bg-muted/20 px-4 py-4 space-y-3">{children}</div>}
      </div>
    )
  }

  return (
    <CollapsibleSection title="Comms Setup" subtitle="Configure chat channels, repo access, and workspace connectors">
      <div className="divide-y rounded-lg border">
        {LEGACY_COMMS_VISIBLE && (
          <>
            <CommsAccordionItem id="telegram" label="Telegram" configured={Boolean(modelsConfig?.comms?.telegram?.configured)}
              detail={`Linked chats: ${modelsConfig?.comms?.telegram?.linked_chats ?? 0}`}>
              <input type="password" value={commsForm.telegram.bot_token} onChange={(e) => onCommsTextChange("telegram", "bot_token", e.target.value)}
                placeholder="Paste Telegram bot token" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
              <input type="text" value={commsForm.telegram.chat_id} onChange={(e) => onCommsTextChange("telegram", "chat_id", e.target.value)}
                placeholder="Telegram chat ID" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
              <label className="flex items-center justify-between gap-2 text-xs">
                <span>Enable polling</span>
                <input type="checkbox" checked={commsForm.telegram.enabled} onChange={(e) => onCommsToggleChange("telegram", "enabled", e.target.checked)} />
              </label>
              <label className="flex items-center justify-between gap-2 text-xs">
                <span>Private only</span>
                <input type="checkbox" checked={commsForm.telegram.private_only} onChange={(e) => onCommsToggleChange("telegram", "private_only", e.target.checked)} />
              </label>
            </CommsAccordionItem>

            <CommsAccordionItem id="discord" label="Discord" configured={Boolean(modelsConfig?.comms?.discord?.configured)}>
              <input type="password" value={commsForm.discord.bot_token} onChange={(e) => onCommsTextChange("discord", "bot_token", e.target.value)}
                placeholder="Paste Discord bot token" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
              <label className="flex items-center justify-between gap-2 text-xs">
                <span>Enable bridge</span>
                <input type="checkbox" checked={commsForm.discord.enabled} onChange={(e) => onCommsToggleChange("discord", "enabled", e.target.checked)} />
              </label>
              <label className="flex items-center justify-between gap-2 text-xs">
                <span>DM only</span>
                <input type="checkbox" checked={commsForm.discord.dm_only} onChange={(e) => onCommsToggleChange("discord", "dm_only", e.target.checked)} />
              </label>
            </CommsAccordionItem>

            <CommsAccordionItem id="whatsapp" label="WhatsApp" configured={Boolean(modelsConfig?.comms?.whatsapp?.configured)}>
              <input type="password" value={commsForm.whatsapp.token} onChange={(e) => onCommsTextChange("whatsapp", "token", e.target.value)}
                placeholder="Paste WhatsApp token" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
              <input type="text" value={commsForm.whatsapp.phone_id} onChange={(e) => onCommsTextChange("whatsapp", "phone_id", e.target.value)}
                placeholder="WhatsApp phone ID" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
              <label className="flex items-center justify-between gap-2 text-xs">
                <span>Enable bridge</span>
                <input type="checkbox" checked={commsForm.whatsapp.enabled} onChange={(e) => onCommsToggleChange("whatsapp", "enabled", e.target.checked)} />
              </label>
            </CommsAccordionItem>
          </>
        )}

        <CommsAccordionItem id="github" label="GitHub" configured={Boolean(modelsConfig?.comms?.github?.configured)}
          detail={`Linked threads: ${modelsConfig?.comms?.github?.linked_threads ?? 0}`}>
          <div className="grid gap-2 rounded-md border bg-background/70 p-3 text-[10px] text-muted-foreground sm:grid-cols-3">
            <span>Token: {modelsConfig?.comms?.github?.token_configured ? "ready" : "missing"}</span>
            <span>SSH: {modelsConfig?.comms?.github?.ssh_configured ? "ready" : "missing"}</span>
            <span>GitHub App: {modelsConfig?.comms?.github?.app_configured ? "ready" : "missing"}</span>
          </div>
          <input type="password" value={commsForm.github.token} onChange={(e) => onCommsTextChange("github", "token", e.target.value)}
            placeholder="Fine-grained PAT" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
          <div className="grid gap-2 md:grid-cols-2">
            <input type="text" value={commsForm.github.ssh_key_path} onChange={(e) => onCommsTextChange("github", "ssh_key_path", e.target.value)}
              placeholder="SSH key path" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
            <input type="password" value={commsForm.github.ssh_private_key} onChange={(e) => onCommsTextChange("github", "ssh_private_key", e.target.value)}
              placeholder="Or paste SSH private key" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
          </div>
          <input type="text" value={commsForm.github.bot_login} onChange={(e) => onCommsTextChange("github", "bot_login", e.target.value)}
            placeholder="Bot login (e.g. sparkbot)" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
          <input type="text" value={commsForm.github.default_repo} onChange={(e) => onCommsTextChange("github", "default_repo", e.target.value)}
            placeholder="Default repo (owner/repo)" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
          <input type="text" value={commsForm.github.allowed_repos} onChange={(e) => onCommsTextChange("github", "allowed_repos", e.target.value)}
            placeholder="Allowed repos (comma-separated)" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
        </CommsAccordionItem>

        {LEGACY_COMMS_VISIBLE && (
          <>
            <CommsAccordionItem id="gmail" label="Gmail" configured={Boolean(modelsConfig?.comms?.google?.gmail_configured)}>
              <input type="password" value={commsForm.google.client_id} onChange={(e) => onCommsTextChange("google", "client_id", e.target.value)}
                placeholder="Google Client ID" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
              <input type="password" value={commsForm.google.client_secret} onChange={(e) => onCommsTextChange("google", "client_secret", e.target.value)}
                placeholder="Google Client Secret" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
              <input type="password" value={commsForm.google.refresh_token} onChange={(e) => onCommsTextChange("google", "refresh_token", e.target.value)}
                placeholder="Google Refresh Token" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
            </CommsAccordionItem>

            <CommsAccordionItem id="google_calendar" label="Google Calendar" configured={Boolean(modelsConfig?.comms?.google?.calendar_configured)}>
              <input type="password" value={commsForm.google.client_id} onChange={(e) => onCommsTextChange("google", "client_id", e.target.value)}
                placeholder="Google Client ID (shared)" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
              <input type="text" value={commsForm.google.calendar_id} onChange={(e) => onCommsTextChange("google", "calendar_id", e.target.value)}
                placeholder="Calendar ID (e.g. primary)" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
            </CommsAccordionItem>

            <CommsAccordionItem id="google_drive" label="Google Drive & Docs" configured={Boolean(modelsConfig?.comms?.google?.drive_configured)}>
              <input type="text" value={commsForm.google.shared_drive_id} onChange={(e) => onCommsTextChange("google", "shared_drive_id", e.target.value)}
                placeholder="Optional shared drive ID" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
            </CommsAccordionItem>
          </>
        )}

        <CommsAccordionItem id="microsoft" label="Microsoft 365" configured={Boolean(modelsConfig?.comms?.microsoft?.configured)}>
          <input type="password" value={commsForm.microsoft.client_id} onChange={(e) => onCommsTextChange("microsoft", "client_id", e.target.value)}
            placeholder="Microsoft Client ID" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
          <input type="password" value={commsForm.microsoft.client_secret} onChange={(e) => onCommsTextChange("microsoft", "client_secret", e.target.value)}
            placeholder="Microsoft Client Secret" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
          <input type="text" value={commsForm.microsoft.tenant_id} onChange={(e) => onCommsTextChange("microsoft", "tenant_id", e.target.value)}
            placeholder="Tenant ID" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
          <input type="password" value={commsForm.microsoft.refresh_token} onChange={(e) => onCommsTextChange("microsoft", "refresh_token", e.target.value)}
            placeholder="Microsoft Refresh Token" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
        </CommsAccordionItem>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <div className="text-xs text-muted-foreground">
          Connector settings are saved locally.
        </div>
        <button type="button" onClick={onSaveComms} disabled={savingComms}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50">
          {savingComms ? "Saving..." : "Save comms"}
        </button>
      </div>
    </CollapsibleSection>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// AGENTS PANEL
// ═══════════════════════════════════════════════════════════════════════════════

export function AgentsPanel(props: SetupPanelProps) {
  const {
    modelsConfig, agentOverrides, openRouterModels,
    savingAgentOverrides, spawning,
    spawnTemplate, spawnName, spawnEmoji, spawnDescription, spawnPrompt,
    agents,
    onAgentOverrideChange, onSaveAgentOverrides,
    onSpawnTemplateChange, onSpawnNameChange, onSpawnEmojiChange,
    onSpawnDescriptionChange, onSpawnPromptChange, onSpawnAgent,
  } = props

  const { localModelOptions, directProviderModels, routingAgents } = useSetupHelpers(props)

  return (
    <CollapsibleSection title="Agents" subtitle="Spawn custom agents, route agent models, and review built-ins">
      {/* Spawn new agent */}
      <div className="mb-4 rounded-lg border bg-background/70 p-4">
        <div className="mb-3">
          <h3 className="text-sm font-semibold">Spawn Agent</h3>
          <p className="text-xs text-muted-foreground">Activate a specialty agent via <code className="rounded bg-muted px-1">@mention</code>.</p>
        </div>
        <div className="grid gap-3 rounded-lg bg-muted/40 p-3 md:grid-cols-2">
          <div className="md:col-span-2">
            <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted-foreground">Agent template</label>
            <select value={spawnTemplate}
              onChange={e => {
                const tpl = AGENT_TEMPLATES.find(t => t.id === e.target.value)
                onSpawnTemplateChange(e.target.value)
                if (tpl) {
                  onSpawnNameChange(tpl.id === "custom" ? "" : tpl.id)
                  onSpawnEmojiChange(tpl.emoji)
                  onSpawnDescriptionChange(tpl.description)
                  onSpawnPromptChange(tpl.prompt)
                }
              }}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none">
              {AGENT_TEMPLATES.map(t => (<option key={t.id} value={t.id}>{t.emoji} {t.label}</option>))}
            </select>
          </div>
          <div className="flex gap-2">
            <div className="w-20 shrink-0">
              <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted-foreground">Emoji</label>
              <input value={spawnEmoji} onChange={e => onSpawnEmojiChange(e.target.value)} maxLength={4}
                className="w-full rounded-md border bg-background px-3 py-2 text-center text-lg outline-none" />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted-foreground">Name</label>
              <input value={spawnName} onChange={e => onSpawnNameChange(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
                placeholder="e.g. sysadmin" className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted-foreground">Short description</label>
            <input value={spawnDescription} onChange={e => onSpawnDescriptionChange(e.target.value)}
              placeholder="One-line description" maxLength={300}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none" />
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted-foreground">System prompt</label>
            <textarea value={spawnPrompt} onChange={e => onSpawnPromptChange(e.target.value)}
              placeholder="Instructions that define this agent's behavior…" rows={4}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono outline-none resize-none" />
          </div>
          <div className="md:col-span-2 flex justify-end">
            <button type="button" onClick={onSpawnAgent} disabled={spawning || !spawnName.trim() || !spawnPrompt.trim()}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50">
              {spawning ? "Spawning..." : "Spawn agent"}
            </button>
          </div>
        </div>
      </div>

      {/* Agent model overrides */}
      <div className="rounded-lg border bg-background/70 p-4 mb-4">
        <div className="mb-3">
          <h3 className="text-sm font-semibold">Model Overrides</h3>
          <p className="text-xs text-muted-foreground">Force agents to a specific provider and model.</p>
        </div>
        <div className="space-y-3">
          {routingAgents.map((agent) => {
            const override = agentOverrides[agent.name] ?? { route: "default", model: "" }
            const route = override.route
            const modelValue = override.model ?? ""
            const routeProviderMap: Record<string, string> = {
              openrouter: "openrouter", local: "ollama", openai: "openai", openai_codex: "openai_codex",
              anthropic: "anthropic", google: "google", groq: "groq", minimax: "minimax", xai: "xai",
            }
            const routeLabels: Record<string, string> = {
              openrouter: "OpenRouter", local: "Local (Ollama)", openai: "OpenAI", openai_codex: "Codex Subscription",
              anthropic: "Anthropic", google: "Google", groq: "Groq", minimax: "MiniMax", xai: "xAI",
            }
            const providerForRoute = routeProviderMap[route] ?? ""
            const modelsForRoute = route === "openrouter"
              ? openRouterModels.map((m) => m.id)
              : route === "local"
                ? localModelOptions
                : providerForRoute
                  ? directProviderModels(providerForRoute)
                  : []

            return (
              <div key={agent.name} className="rounded-lg border bg-muted/30 px-3 py-3">
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-base">{agent.emoji}</span>
                  <div>
                    <div className="text-sm font-medium">{agent.name === "sparkbot" ? "Sparkbot main chat" : agentDisplayName(agent.name)}</div>
                    {agent.name !== "sparkbot" && <div className="font-mono text-[11px] text-muted-foreground">@{agent.name}</div>}
                    <div className="text-[11px] text-muted-foreground">{agent.description}</div>
                  </div>
                </div>
                <div className="grid gap-2">
                  <select value={route} onChange={(e) => onAgentOverrideChange(agent.name, "route", e.target.value)}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none">
                    <option value="default">Use default</option>
                    <option value="openai">OpenAI</option>
                    <option value="openai_codex">Codex Subscription</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="google">Google</option>
                    <option value="groq">Groq</option>
                    <option value="minimax">MiniMax</option>
                    <option value="xai">xAI</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="local">Local (Ollama)</option>
                  </select>
                  {route !== "default" && modelsForRoute.length > 0 && (
                    <select value={modelValue} onChange={(e) => onAgentOverrideChange(agent.name, "model", e.target.value)}
                      className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none">
                      <option value="">{`Use default ${routeLabels[route] ?? route} model`}</option>
                      {modelsForRoute.map((modelId) => (
                        <option key={modelId} value={modelId}>
                          {route === "openrouter"
                            ? openRouterModels.find((m) => m.id === modelId)?.label ?? modelId
                            : modelsConfig?.model_labels?.[modelId] ?? modelId}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>
            )
          })}
        </div>
        <div className="mt-4 flex justify-end">
          <button type="button" onClick={onSaveAgentOverrides} disabled={savingAgentOverrides}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50">
            {savingAgentOverrides ? "Saving overrides..." : "Save overrides"}
          </button>
        </div>
      </div>

      {/* Built-in agents reference */}
      <div className="rounded-lg border bg-background/70 p-4">
        <h3 className="mb-3 text-sm font-semibold">Built-in agents</h3>
        <div className="flex flex-wrap gap-2">
          {agents.filter(a => a.is_builtin !== false).map(agent => (
            <span key={agent.name} className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs">
              {agent.emoji} {agentDisplayName(agent.name)}
            </span>
          ))}
        </div>
      </div>
    </CollapsibleSection>
  )
}
