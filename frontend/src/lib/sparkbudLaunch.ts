export interface SparkBudLaunchConfig {
  stationId: "sb-researcher" | "sb-coder" | "sb-analyst" | "sb-custom"
  label: string
  launchMode: "builtin" | "custom"
  mentionName?: string
  defaultHandle?: string
  emoji: string
  summary: string
  helperText: string
  defaultPrompt: string
}

const SPARKBUD_CHAT_LAUNCH_DRAFT_KEY = "sparkbot_sparkbud_chat_launch_draft"

const SPARKBUD_CONFIG: Record<SparkBudLaunchConfig["stationId"], SparkBudLaunchConfig> = {
  "sb-researcher": {
    stationId: "sb-researcher",
    label: "Researcher",
    launchMode: "builtin",
    mentionName: "researcher",
    emoji: "🔍",
    summary: "Gather facts, compare sources, call out uncertainty, and return a structured summary with next steps.",
    helperText: "This launch prompt becomes the opening brief sent to @researcher in chat.",
    defaultPrompt: `Research brief
- Goal:
- Sources or options to compare:
- Known uncertainty:
- Deliverable: structured summary with next steps`,
  },
  "sb-coder": {
    stationId: "sb-coder",
    label: "Coder",
    launchMode: "builtin",
    mentionName: "coder",
    emoji: "💻",
    summary: "Implement, debug, or refactor with concrete technical output and clear verification steps.",
    helperText: "This launch prompt becomes the opening brief sent to @coder in chat.",
    defaultPrompt: `Build brief
- Objective:
- Codebase or file area:
- Constraints:
- Deliverable: concrete implementation plus verification steps`,
  },
  "sb-analyst": {
    stationId: "sb-analyst",
    label: "Analyst",
    launchMode: "builtin",
    mentionName: "analyst",
    emoji: "📊",
    summary: "Break down the problem, surface patterns and tradeoffs, and recommend a decision path.",
    helperText: "This launch prompt becomes the opening brief sent to @analyst in chat.",
    defaultPrompt: `Analysis brief
- Decision or problem:
- Key signals or data:
- Risks and tradeoffs:
- Deliverable: recommended path with reasoning`,
  },
  "sb-custom": {
    stationId: "sb-custom",
    label: "Custom",
    launchMode: "custom",
    defaultHandle: "specialist",
    emoji: "🤖",
    summary: "Define a specialist role in plain language, then launch it as a named custom agent for this workspace.",
    helperText: "This prompt becomes the specialist's behavior profile. After launch, the agent opens in chat ready for @mention use.",
    defaultPrompt: `You are a custom SparkBud specialist.

Role:
Primary responsibilities:
Working style:
Output format:
When uncertainty remains, say so clearly and list the next information needed.`,
  },
}

export interface SparkBudLaunchDraft {
  text: string
}

export function getSparkBudLaunchConfig(stationId: string): SparkBudLaunchConfig | null {
  return SPARKBUD_CONFIG[stationId as SparkBudLaunchConfig["stationId"]] ?? null
}

export function buildSparkBudChatLaunchText(mentionName: string, prompt: string): string {
  const trimmedPrompt = prompt.trim()
  return trimmedPrompt ? `@${mentionName}\n${trimmedPrompt}` : `@${mentionName} `
}

export function saveSparkBudChatLaunchDraft(draft: SparkBudLaunchDraft): void {
  if (typeof window === "undefined") return
  window.sessionStorage.setItem(SPARKBUD_CHAT_LAUNCH_DRAFT_KEY, JSON.stringify(draft))
}

export function consumeSparkBudChatLaunchDraft(): SparkBudLaunchDraft | null {
  if (typeof window === "undefined") return null
  const raw = window.sessionStorage.getItem(SPARKBUD_CHAT_LAUNCH_DRAFT_KEY)
  if (!raw) return null
  window.sessionStorage.removeItem(SPARKBUD_CHAT_LAUNCH_DRAFT_KEY)
  try {
    return JSON.parse(raw) as SparkBudLaunchDraft
  } catch {
    return null
  }
}
