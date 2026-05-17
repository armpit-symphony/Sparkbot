export type SparkbotSurfaceTab =
  | "chat"
  | "workstation"
  | "robo_os"
  | "spine_ops"
  | "info"

interface SparkbotSurfaceTabsProps {
  active?: SparkbotSurfaceTab
  onChat: () => void
  onWorkstation: () => void
  onControls?: () => void // kept for backwards compat — redirects to Command Center
  onRoboOs?: () => void
  onSpineOps?: () => void
  onInfo?: () => void
}

const TAB_BORDER = "rgba(59, 130, 246, 0.20)"
const TAB_IDLE_BG = "rgba(7, 13, 28, 0.76)"
const TAB_ACTIVE_BG =
  "linear-gradient(135deg, rgba(37,99,235,0.28), rgba(59,130,246,0.20), rgba(96,165,250,0.14))"
const TAB_ACTIVE_BORDER = "rgba(59, 130, 246, 0.50)"
const TAB_ACTIVE_SHADOW = "0 10px 24px rgba(30, 64, 175, 0.24)"

const TAB_CONFIG: Array<{
  id: SparkbotSurfaceTab
  label: "Chat" | "Workstation" | "Robo" | "Command Center" | "Info"
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
    id: "robo_os",
    label: "Robo",
    onClick: (props) => {
      if (props.onRoboOs) {
        props.onRoboOs()
        return
      }
      props.onWorkstation()
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
                ? "text-blue-50"
                : "text-slate-300 hover:text-slate-50 hover:bg-[rgba(37,99,235,0.08)] hover:border-[rgba(59,130,246,0.24)]"
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
