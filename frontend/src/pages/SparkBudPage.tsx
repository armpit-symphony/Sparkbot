// ─── SparkBudPage.tsx ─────────────────────────────────────────────────────────
// Public-facing gate page for SparkBud routes.
// Deep links stay valid, but the workstation no longer treats these as public-ready.

import { useCallback } from "react"
import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, Clock, Cpu, Zap } from "lucide-react"
import { SPARKBUDS } from "@/config/workstationStations"
import { Button } from "@/components/ui/button"

// ─── Per-bud holdback notes ───────────────────────────────────────────────────

const DESK_HOLDBACK_NOTES: Record<string, string[]> = {
  "sb-research": [
    "Needs a clearer source-validation and browsing story for public users",
    "Needs a simpler explanation of what is live versus aspirational",
    "Should connect to real project context before surfacing as a desk",
    "Should feel like a product surface, not a route preview",
  ],
  "sb-builder": [
    "Needs explicit permissions and repo-safety boundaries",
    "Needs a clearer first-run story than direct deep-link launch",
    "Should avoid reading like an internal coding console",
    "Should return only when the desk workflow is truly productized",
  ],
  "sb-webmaker": [
    "Needs a public-ready design/build workflow with clearer scope",
    "Should avoid implying live deploy control before it exists cleanly",
    "Needs stronger guardrails around edits and publish actions",
    "Should return with clearer outcomes and examples",
  ],
  "sb-automation": [
    "Needs a cleaner separation between personal automation and ops tooling",
    "Should not imply server/operator control by default",
    "Needs clearer safety messaging before public exposure",
    "Should return only after the advanced mode story is settled",
  ],
}

const SCANLINE_BG =
  "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px)"

// ─── SparkBudPage ─────────────────────────────────────────────────────────────

interface SparkBudPageProps {
  budId: string
}

export default function SparkBudPage({ budId }: SparkBudPageProps) {
  const navigate = useNavigate()
  const bud = SPARKBUDS.find((b) => b.id === budId)

  const handleBack = useCallback(() => {
    navigate({ to: "/workstation" })
  }, [navigate])

  if (!bud) {
    return (
      <div
        style={{
          minHeight: "100dvh",
          backgroundColor: "#060a13",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "monospace",
          color: "#4b5563",
        }}
      >
        Unknown SparkBud: {budId}
      </div>
    )
  }

  const { accentHex, label, description, capabilities, icon: Icon } = bud
  const holdbackNotes = DESK_HOLDBACK_NOTES[budId] ?? []

  return (
    <>
      {/* Mobile fallback */}
      <div
        className="flex flex-col items-center justify-center gap-6 sm:hidden"
        style={{
          minHeight: "100dvh",
          backgroundColor: "#060a13",
          padding: 24,
          fontFamily: "monospace",
        }}
      >
        <Icon size={40} style={{ color: accentHex, filter: `drop-shadow(0 0 10px ${accentHex}88)` }} />
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: accentHex, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>
            {label} Agent
          </div>
          <p style={{ fontSize: 12, color: "#6b7280", lineHeight: 1.6, maxWidth: 280, margin: 0 }}>
            This view requires a larger screen.
          </p>
        </div>
        <Button variant="outline" onClick={handleBack}>Back to Workstation</Button>
      </div>

      {/* Full view */}
      <div
        className="hidden sm:flex"
        style={{
          flexDirection: "column",
          minHeight: "100dvh",
          backgroundColor: "#060a13",
          backgroundImage: `
            repeating-linear-gradient(0deg, transparent, transparent 47px, ${accentHex}06 47px, ${accentHex}06 48px),
            repeating-linear-gradient(90deg, transparent, transparent 47px, ${accentHex}06 47px, ${accentHex}06 48px)
          `,
          fontFamily: "monospace",
        }}
      >
        {/* Scanlines */}
        <div
          style={{
            position: "fixed",
            inset: 0,
            backgroundImage: SCANLINE_BG,
            pointerEvents: "none",
            zIndex: 5,
          }}
        />

        {/* Header bar */}
        <header
          style={{
            height: 48,
            borderBottom: "1px solid #0d1f35",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 20px",
            backgroundColor: "#060a13",
            flexShrink: 0,
            zIndex: 10,
            position: "relative",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              onClick={handleBack}
              style={{
                background: "none",
                border: `1px solid #1a2235`,
                borderRadius: 4,
                cursor: "pointer",
                color: "#4b5563",
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 10px",
                fontSize: 11,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                fontFamily: "monospace",
                transition: "border-color 0.15s, color 0.15s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = accentHex
                e.currentTarget.style.color = accentHex
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "#1a2235"
                e.currentTarget.style.color = "#4b5563"
              }}
            >
              <ArrowLeft size={12} />
              Workstation
            </button>
            <div style={{ width: 1, height: 20, backgroundColor: "#1a2235" }} />
            <Icon
              size={16}
              style={{ color: accentHex, filter: `drop-shadow(0 0 6px ${accentHex}88)` }}
            />
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: accentHex,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              }}
            >
              {label} SparkBud
            </span>
          </div>
          <div
            style={{
              fontSize: 10,
              color: "#64748b",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              border: "1px solid #1a2235",
              borderRadius: 3,
              padding: "2px 8px",
            }}
          >
            Hidden from public flow
          </div>
        </header>

        {/* Main content */}
        <main
          style={{
            flex: 1,
            padding: 24,
            display: "flex",
            flexDirection: "column",
            gap: 20,
            position: "relative",
            zIndex: 6,
            maxWidth: 960,
            margin: "0 auto",
            width: "100%",
          }}
        >
          {/* Agent hero card */}
          <div
            style={{
              backgroundColor: "#0a1120",
              border: `1px solid ${accentHex}44`,
              borderRadius: 10,
              overflow: "hidden",
              boxShadow: `0 0 32px 4px ${accentHex}18`,
            }}
          >
            {/* Accent header */}
            <div
              style={{
                backgroundColor: `${accentHex}14`,
                borderBottom: `1px solid ${accentHex}33`,
                padding: "20px 24px",
                display: "flex",
                alignItems: "center",
                gap: 16,
              }}
            >
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: 8,
                  backgroundColor: "#030508",
                  border: `1px solid ${accentHex}44`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  boxShadow: `0 0 16px 2px ${accentHex}33`,
                  backgroundImage: SCANLINE_BG,
                  flexShrink: 0,
                }}
              >
                <Icon
                  size={28}
                  style={{
                    color: accentHex,
                    filter: `drop-shadow(0 0 8px ${accentHex}88)`,
                  }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <div
                  style={{
                    fontSize: 18,
                    fontWeight: 700,
                    color: accentHex,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    marginBottom: 4,
                  }}
                >
                  {label} desk
                </div>
                <div style={{ fontSize: 11, color: "#6b7280", letterSpacing: "0.04em" }}>
                  Specialist desk · {budId}
                </div>
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  backgroundColor: `${accentHex}12`,
                  border: `1px solid ${accentHex}33`,
                  borderRadius: 6,
                  padding: "8px 14px",
                }}
              >
                <Clock size={13} style={{ color: accentHex }} />
                <span
                  style={{
                    fontSize: 11,
                    color: accentHex,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    fontWeight: 700,
                  }}
                >
                  Not public yet
                </span>
              </div>
            </div>

            {/* Description */}
            <div style={{ padding: "16px 24px", borderBottom: `1px solid #0d1f35` }}>
              <p style={{ fontSize: 12, color: "#9ca3af", lineHeight: 1.7, margin: 0 }}>
                {description} This route is intentionally held back from the public workstation
                until the desk flow is clearer, more complete, and easier to explain.
              </p>
            </div>

            {/* Two-column body */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 0,
              }}
            >
              {/* Capabilities */}
              <div
                style={{
                  padding: "16px 24px",
                  borderRight: `1px solid #0d1f35`,
                }}
              >
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: "#4b5563",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    marginBottom: 12,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <Cpu size={11} style={{ color: "#4b5563" }} />
                  Desk focus
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {capabilities.map((cap) => (
                    <div
                      key={cap}
                      style={{ display: "flex", alignItems: "center", gap: 8 }}
                    >
                      <span
                        style={{
                          width: 6,
                          height: 6,
                          borderRadius: "50%",
                          backgroundColor: `${accentHex}66`,
                          border: `1px solid ${accentHex}`,
                          flexShrink: 0,
                        }}
                      />
                      <span style={{ fontSize: 11, color: "#9ca3af", letterSpacing: "0.03em" }}>
                        {cap}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Phase 3 roadmap */}
              <div style={{ padding: "16px 24px" }}>
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: "#4b5563",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    marginBottom: 12,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <Zap size={11} style={{ color: "#4b5563" }} />
                  Why it is hidden today
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {holdbackNotes.map((item) => (
                    <div
                      key={item}
                      style={{ display: "flex", alignItems: "flex-start", gap: 8 }}
                    >
                      <span
                        style={{
                          fontSize: 10,
                          color: "#1f2937",
                          marginTop: 2,
                          flexShrink: 0,
                          letterSpacing: "0.04em",
                        }}
                      >
                        ○
                      </span>
                      <span style={{ fontSize: 11, color: "#6b7280", lineHeight: 1.5, letterSpacing: "0.03em" }}>
                        {item}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Status notice */}
          <div
            style={{
              backgroundColor: "#0a1120",
              border: "1px solid #1a2235",
              borderRadius: 8,
              padding: "14px 20px",
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                backgroundColor: "#fbbf24",
                boxShadow: "0 0 6px 2px #fbbf2466",
                flexShrink: 0,
              }}
            />
            <p style={{ fontSize: 11, color: "#6b7280", margin: 0, lineHeight: 1.6 }}>
              <span style={{ color: "#9ca3af", fontWeight: 700 }}>Public holdback —</span>{" "}
              Specialist desks stay out of the public workstation until they have a cleaner setup
              path, clearer permissions story, and a more complete end-to-end experience.
            </p>
          </div>
        </main>

        {/* Footer */}
        <footer
          style={{
            height: 36,
            borderTop: "1px solid #0d1f35",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: "#060a13",
            flexShrink: 0,
            zIndex: 10,
            position: "relative",
          }}
        >
          <span style={{ fontSize: 10, color: "#1e3a52", letterSpacing: "0.08em" }}>
            SparkPit Labs · Specialist desk routes are intentionally gated
          </span>
        </footer>
      </div>
    </>
  )
}
