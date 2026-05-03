export type SparkbotSurfaceTab =
  | "chat"
  | "workstation"
  | "controls"
  | "robo_os"
  | "spine_ops"
  | "info"

interface SparkbotSurfaceTabsProps {
  active?: SparkbotSurfaceTab
  onChat: () => void
  onWorkstation: () => void
  onControls: () => void
  onRoboOs?: () => void
  onSpineOps?: () => void
  onInfo?: () => void
}

const TAB_BORDER = "rgba(129, 140, 248, 0.16)"
const TAB_IDLE_BG = "rgba(7, 13, 28, 0.76)"
const TAB_ACTIVE_BG =
  "linear-gradient(135deg, rgba(79,70,229,0.28), rgba(59,130,246,0.16), rgba(168,85,247,0.14))"
const TAB_ACTIVE_BORDER = "rgba(129, 140, 248, 0.42)"
const TAB_ACTIVE_SHADOW = "0 10px 24px rgba(49, 46, 129, 0.24)"

const TAB_CONFIG: Array<{
  id: SparkbotSurfaceTab
  label: "Chat" | "Workstation" | "Controls" | "Robo OS" | "Command Center" | "Info"
  onClick: (props: SparkbotSurfaceTabsProps) => void
}> = [
  {
    id: "chat",
    label: "Chat",
    onClick: (props) => props.onChat(),
  },
  {
    id: "workstation",
    label: "Workstation",
    onClick: (props) => props.onWorkstation(),
  },
  {
    id: "controls",
    label: "Controls",
    onClick: (props) => props.onControls(),
  },
  {
    id: "robo_os",
    label: "Robo OS",
    onClick: (props) => {
      if (props.onRoboOs) {
        props.onRoboOs()
        return
      }
      window.open("https://github.com/armpit-symphony/LIMA-Robo-OS", "_blank", "noopener,noreferrer")
    },
  },
  {
    id: "spine_ops",
    label: "Command Center",
    onClick: (props) => props.onSpineOps?.(),
  },
  {
    id: "info",
    label: "Info",
    onClick: (props) => props.onInfo?.(),
  },
]

export default function SparkbotSurfaceTabs(props: SparkbotSurfaceTabsProps) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {TAB_CONFIG.filter((tab) => {
        if (tab.id === "info" && !props.onInfo) return false
        if (tab.id === "spine_ops" && !props.onSpineOps) return false
        return true
      }).map((tab) => {
        const isActive = props.active === tab.id

        return (
          <button
            key={tab.id}
            type="button"
            aria-current={isActive ? "page" : undefined}
            onClick={() => {
              if (!isActive) tab.onClick(props)
            }}
            className={`inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-medium tracking-[0.08em] transition-all ${
              isActive
                ? "text-indigo-50"
                : "text-slate-300 hover:text-slate-50 hover:bg-[rgba(79,70,229,0.08)] hover:border-[rgba(129,140,248,0.24)]"
            }`}
            style={{
              borderColor: isActive ? TAB_ACTIVE_BORDER : TAB_BORDER,
              background: isActive ? TAB_ACTIVE_BG : TAB_IDLE_BG,
              boxShadow: isActive ? TAB_ACTIVE_SHADOW : "none",
              cursor: isActive ? "default" : "pointer",
            }}
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}
