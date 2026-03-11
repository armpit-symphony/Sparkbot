import { X } from "lucide-react"

interface SparkbotSurfaceInfoDialogProps {
  open: boolean
  title: string
  subtitle: string
  bullets: string[]
  onClose: () => void
}

export default function SparkbotSurfaceInfoDialog({
  open,
  title,
  subtitle,
  bullets,
  onClose,
}: SparkbotSurfaceInfoDialogProps) {
  if (!open) return null

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          backgroundColor: "rgba(3, 7, 18, 0.72)",
          backdropFilter: "blur(3px)",
          zIndex: 70,
        }}
      />
      <div
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "min(92vw, 520px)",
          background:
            "linear-gradient(180deg, rgba(7,11,24,0.98), rgba(10,16,31,0.96))",
          border: "1px solid rgba(99,102,241,0.22)",
          borderRadius: 18,
          boxShadow: "0 24px 64px rgba(0,0,0,0.42)",
          zIndex: 71,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: "16px 18px",
            borderBottom: "1px solid rgba(99,102,241,0.16)",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 16,
          }}
        >
          <div>
            <div
              style={{
                fontSize: 11,
                color: "#8b93ff",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                fontWeight: 700,
              }}
            >
              Info
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, color: "#e2e8f0", marginTop: 6 }}>
              {title}
            </div>
            <p style={{ fontSize: 13, color: "#94a3b8", lineHeight: 1.7, margin: "8px 0 0" }}>
              {subtitle}
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            style={{
              width: 32,
              height: 32,
              borderRadius: 999,
              border: "1px solid rgba(99,102,241,0.16)",
              backgroundColor: "rgba(7, 13, 28, 0.72)",
              color: "#94a3b8",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
            aria-label="Close info"
          >
            <X size={15} />
          </button>
        </div>

        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
          {bullets.map((bullet) => (
            <div
              key={bullet}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
                border: "1px solid rgba(99,102,241,0.12)",
                borderRadius: 12,
                backgroundColor: "rgba(7, 13, 28, 0.6)",
                padding: "12px 14px",
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  backgroundColor: "#7dd3fc",
                  boxShadow: "0 0 10px rgba(125,211,252,0.28)",
                  marginTop: 6,
                  flexShrink: 0,
                }}
              />
              <span style={{ fontSize: 13, color: "#cbd5e1", lineHeight: 1.65 }}>{bullet}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
