import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { apiFetch } from "@/lib/apiBase"
import { ArrowLeft, Info, Loader2, Users } from "lucide-react"
import SparkbotSurfaceTabs from "@/components/Common/SparkbotSurfaceTabs"
import SparkbotSurfaceInfoDialog from "@/components/Common/SparkbotSurfaceInfoDialog"
import ChatInput from "@/components/chat/ChatInput"
import ChatWindow from "@/components/chat/ChatWindow"
import {
  deleteMeetingRoomMeta,
  launchMeetingRoom,
  listMeetingRoomMetas,
  loadMeetingRoomMeta,
  type WorkstationMeetingRoomMeta,
} from "@/lib/workstationMeeting"
import type { Message, User } from "@/lib/chat/types"

interface MeetingRoomPageProps {
  roomId: string
}

interface RoomDetail {
  id: string
  name: string
  description?: string
  meeting_mode_enabled: boolean
  meeting_mode_bots_mention_only: boolean
  meeting_mode_max_bot_msgs_per_min: number
}

interface RoomMemberMeResponse {
  user: User
}

interface MeetingListItem {
  id: string
  name: string
  description?: string
  created_at: string
  updated_at: string
  meeting_mode_enabled: boolean
  meta: WorkstationMeetingRoomMeta | null
}

export default function MeetingRoomPage({ roomId }: MeetingRoomPageProps) {
  const navigate = useNavigate()
  const [room, setRoom] = useState<RoomDetail | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [inputValue, setInputValue] = useState("")
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [infoOpen, setInfoOpen] = useState(false)
  const [meetingMeta, setMeetingMeta] = useState<WorkstationMeetingRoomMeta | null>(null)
  const [generatingNotes, setGeneratingNotes] = useState(false)
  const [latestArtifact, setLatestArtifact] = useState<{
    id: string
    content_markdown: string
    created_at: string
  } | null>(null)
  const [streamingToken, setStreamingToken] = useState("")
  const [streamingAgent, setStreamingAgent] = useState<string | null>(null)
  const [streamError, setStreamError] = useState("")
  const [sidebarTab, setSidebarTab] = useState<"current" | "meetings" | "tasks">("current")
  const [meetingRooms, setMeetingRooms] = useState<MeetingListItem[]>([])
  const [meetingActionId, setMeetingActionId] = useState<string | null>(null)
  const [roomTasks, setRoomTasks] = useState<Array<{
    id: string; name: string; tool_name: string; schedule: string;
    enabled: boolean; last_status: string | null; last_run_at: string | null;
    consecutive_failures: number;
  }>>([])
  const [runningTaskId, setRunningTaskId] = useState<string | null>(null)
  const streamAbortRef = useRef<AbortController | null>(null)
  const activeStreamIdRef = useRef(0)

  useEffect(() => {
    setMeetingMeta(loadMeetingRoomMeta(roomId))
  }, [roomId])

  useEffect(() => {
    if (!roomId) return
    apiFetch(`/api/v1/chat/rooms/${roomId}/artifacts?type=notes&limit=1`, {
      credentials: "include",
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((artifacts: Array<{ id: string; content_markdown: string; created_at: string }>) => {
        if (artifacts.length > 0) setLatestArtifact(artifacts[0])
      })
      .catch(() => {})
  }, [roomId])

  useEffect(() => {
    let cancelled = false

    async function loadRoomState() {
      try {
        const [roomRes, messagesRes, meRes] = await Promise.all([
          apiFetch(`/api/v1/chat/rooms/${roomId}`, { credentials: "include" }),
          apiFetch(`/api/v1/chat/rooms/${roomId}/messages`, { credentials: "include" }),
          apiFetch(`/api/v1/chat/rooms/${roomId}/members/me`, { credentials: "include" }),
        ])

        if (!cancelled && roomRes.ok) {
          setRoom(await roomRes.json())
        }

        if (!cancelled && messagesRes.ok) {
          const messageData = await messagesRes.json()
          setMessages(messageData.messages ?? [])
        }

        if (!cancelled && meRes.ok) {
          const membership = (await meRes.json()) as RoomMemberMeResponse
          setCurrentUser(membership.user ?? null)
        }
        if (!cancelled) {
          await Promise.all([reloadMeetingRooms(), reloadRoomTasks()])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadRoomState()

    return () => {
      cancelled = true
    }
  }, [roomId])

  const seatedParticipants = useMemo(
    () => meetingMeta?.seats ?? [],
    [meetingMeta],
  )

  const reloadRoomTasks = async () => {
    try {
      const res = await apiFetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks?limit=20`, {
        credentials: "include",
      })
      if (!res.ok) return
      const data = await res.json()
      setRoomTasks(data.items ?? [])
    } catch {
      // guardian may not have tasks for this room
    }
  }

  const reloadMeetingRooms = async () => {
    const res = await apiFetch("/api/v1/chat/rooms/", { credentials: "include" })
    if (!res.ok) return
    const rooms = await res.json()
    const metaIndex = new Map(listMeetingRoomMetas().map((meta) => [meta.roomId, meta]))
    const nextRooms = (Array.isArray(rooms) ? rooms : [])
      .filter((candidate) => candidate.meeting_mode_enabled)
      .map((candidate) => ({
        id: candidate.id,
        name: candidate.name,
        description: candidate.description,
        created_at: candidate.created_at,
        updated_at: candidate.updated_at,
        meeting_mode_enabled: candidate.meeting_mode_enabled,
        meta: metaIndex.get(candidate.id) ?? null,
      }))
      .sort(
        (left, right) =>
          Date.parse(right.updated_at || right.created_at || "") -
          Date.parse(left.updated_at || left.created_at || ""),
      )
    setMeetingRooms(nextRooms)
  }

  const reloadMessages = async () => {
    const [messagesRes, artifactRes] = await Promise.all([
      apiFetch(`/api/v1/chat/rooms/${roomId}/messages`, { credentials: "include" }),
      apiFetch(`/api/v1/chat/rooms/${roomId}/artifacts?type=notes&limit=1`, { credentials: "include" }),
    ])
    if (messagesRes.ok) {
      const data = await messagesRes.json()
      setMessages(data.messages ?? [])
    }
    if (artifactRes.ok) {
      const artifacts = await artifactRes.json()
      setLatestArtifact(artifacts?.[0] ?? null)
    }
    await reloadMeetingRooms()
  }

  async function handleStartFreshMeeting() {
    if (meetingActionId || seatedParticipants.length < 2) return
    setMeetingActionId("new")
    setStreamError("")
    try {
      const nextMeeting = await launchMeetingRoom({
        roomName: room?.name ?? meetingMeta?.roomName ?? "Roundtable",
        seats: seatedParticipants,
      })
      await reloadMeetingRooms()
      navigate({ to: "/meeting/$roomId", params: { roomId: nextMeeting.roomId } })
    } catch (err) {
      setStreamError((err as Error).message || "Could not start a fresh meeting.")
    } finally {
      setMeetingActionId(null)
    }
  }

  async function handleEndMeeting(targetRoomId: string) {
    if (meetingActionId) return
    if (typeof window !== "undefined" && !window.confirm("End this meeting? It will leave the active list.")) {
      return
    }
    setMeetingActionId(`end:${targetRoomId}`)
    setStreamError("")
    try {
      const target = meetingRooms.find((candidate) => candidate.id === targetRoomId)
      const targetName = target?.name ?? room?.name ?? "Roundtable"
      const targetDescription = target?.description ?? room?.description ?? ""
      const nextDescription = [targetDescription, `Ended ${new Date().toISOString()}`]
        .filter(Boolean)
        .join("\n\n")
      const res = await apiFetch(`/api/v1/chat/rooms/${targetRoomId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          name: targetName.includes("[Ended]") ? targetName : `${targetName} [Ended]`,
          description: nextDescription,
          meeting_mode_enabled: false,
        }),
      })
      if (!res.ok) throw new Error("Could not end meeting.")
      deleteMeetingRoomMeta(targetRoomId)
      await reloadMeetingRooms()
      if (targetRoomId === roomId) {
        streamAbortRef.current?.abort()
        navigate({ to: "/workstation" })
      }
    } catch (err) {
      setStreamError((err as Error).message || "Could not end meeting.")
    } finally {
      setMeetingActionId(null)
    }
  }

  async function handleDeleteMeeting(targetRoomId: string) {
    if (meetingActionId) return
    if (typeof window !== "undefined" && !window.confirm("Delete this meeting permanently?")) {
      return
    }
    setMeetingActionId(`delete:${targetRoomId}`)
    setStreamError("")
    try {
      const res = await apiFetch(`/api/v1/chat/rooms/${targetRoomId}`, {
        method: "DELETE",
        credentials: "include",
      })
      if (!res.ok) throw new Error("Could not delete meeting.")
      deleteMeetingRoomMeta(targetRoomId)
      await reloadMeetingRooms()
      if (targetRoomId === roomId) {
        streamAbortRef.current?.abort()
        navigate({ to: "/workstation" })
      }
    } catch (err) {
      setStreamError((err as Error).message || "Could not delete meeting.")
    } finally {
      setMeetingActionId(null)
    }
  }

  async function handleSendMessage(content: string) {
    if (!content.trim()) return

    // Cancel any in-flight stream
    streamAbortRef.current?.abort()
    const abort = new AbortController()
    streamAbortRef.current = abort
    const streamId = activeStreamIdRef.current + 1
    activeStreamIdRef.current = streamId

    setSending(true)
    setStreamingToken("")
    setStreamingAgent(null)
    setStreamError("")
    setInputValue("")

    // Derive participant handles from seated agents (when no @mention present)
    const hasMention = /^@\w+/.test(content.trim())
    const participants = (!hasMention && seatedParticipants.length > 0)
      ? seatedParticipants.map((s) => s.label.toLowerCase().replace(/\s+/g, ""))
      : undefined

    try {
      const response = await apiFetch(`/api/v1/chat/rooms/${roomId}/messages/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        signal: abort.signal,
        body: JSON.stringify({ content: content.trim(), ...(participants ? { participants } : {}) }),
      })

      if (!response.ok || !response.body) {
        const errText = await response.text().catch(() => "")
        throw new Error(errText || "Could not send meeting message.")
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let accumulated = ""
      let streamDone = false

      while (!streamDone) {
        if (activeStreamIdRef.current !== streamId) break
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data: ")) continue
          if (activeStreamIdRef.current !== streamId) {
            streamDone = true
            break
          }
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === "token") {
              accumulated += evt.token
              setStreamingToken(accumulated)
            } else if (evt.type === "agent_start") {
              // New agent starting — reset accumulated and update label
              accumulated = ""
              setStreamingToken("")
              setStreamingAgent(evt.label || evt.agent || null)
            } else if (evt.type === "agent_done") {
              accumulated = ""
              setStreamingToken("")
              setStreamingAgent(null)
              await reloadMessages()
            } else if (evt.type === "done") {
              streamDone = true
              break
            } else if (evt.type === "error") {
              const msg = typeof evt.error === "string" ? evt.error : "An error occurred."
              const friendly = msg.includes("guardrail") || msg.includes("data policy")
                ? "OpenRouter model unavailable (privacy policy). Check OpenRouter settings or switch model in Controls."
                : msg.includes("NotFoundError") || msg.includes("404")
                ? "Model not found. Please check your model settings in Controls."
                : msg.substring(0, 120)
              setStreamError(friendly)
              streamDone = true
              break
            }
          } catch {
            // malformed SSE line — ignore
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        console.error("Meeting stream error:", err)
        setStreamError((err as Error).message || "Stream error. Check console.")
      }
    } finally {
      if (activeStreamIdRef.current === streamId) {
        setStreamingToken("")
        setStreamingAgent(null)
        setSending(false)
      }
      await reloadMessages()
    }
  }

  async function handleGenerateNotes() {
    if (generatingNotes) return
    setGeneratingNotes(true)
    try {
      const res = await apiFetch(`/api/v1/chat/rooms/${roomId}/artifacts/generate`, {
        method: "POST",
        credentials: "include",
      })
      if (!res.ok) throw new Error("Could not generate notes")
      const artifact = await res.json()
      setLatestArtifact(artifact)
    } catch (err) {
      console.error("Generate notes error:", err)
    } finally {
      setGeneratingNotes(false)
    }
  }

  return (
    <>
      <div
        style={{
          minHeight: "100dvh",
          display: "flex",
          flexDirection: "column",
          background:
            "linear-gradient(180deg, rgba(6,10,19,1), rgba(8,14,28,1), rgba(11,17,33,1))",
        }}
      >
        <header
          style={{
            height: 56,
            borderBottom: "1px solid rgba(99,102,241,0.16)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 20px",
            background:
              "linear-gradient(180deg, rgba(7,11,24,0.98), rgba(10,16,31,0.94))",
            flexShrink: 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              type="button"
              onClick={() => navigate({ to: "/workstation" })}
              style={{
                width: 34,
                height: 34,
                borderRadius: 999,
                border: "1px solid rgba(99,102,241,0.16)",
                backgroundColor: "rgba(7, 13, 28, 0.72)",
                color: "#cbd5f5",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
              aria-label="Back to Workstation"
            >
              <ArrowLeft size={16} />
            </button>
            <div>
              <div
                style={{
                  fontSize: 10,
                  color: "#8b93ff",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  fontWeight: 700,
                }}
              >
                Meeting Room
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: "#e2e8f0", marginTop: 4 }}>
                {room?.name ?? "Roundtable"}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <SparkbotSurfaceTabs
              active={infoOpen ? "info" : undefined}
              onChat={() => navigate({ to: "/dm" })}
              onWorkstation={() => navigate({ to: "/workstation" })}
              onControls={() => navigate({ to: "/dm", search: { controls: "open" } })}
              onInfo={() => setInfoOpen((prev) => !prev)}
            />
            <div
              style={{
                border: "1px solid rgba(125,211,252,0.18)",
                borderRadius: 999,
                padding: "6px 10px",
                fontSize: 10,
                color: "#cbd5f5",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
              }}
            >
              Autonomous meeting
            </div>
          </div>
        </header>

        <main
          style={{
            flex: 1,
            padding: 16,
            display: "grid",
            gridTemplateColumns: "320px minmax(0, 1fr)",
            gap: 16,
          }}
        >
          <aside
            style={{
              border: "1px solid rgba(99,102,241,0.16)",
              borderRadius: 18,
              backgroundColor: "rgba(7, 13, 28, 0.68)",
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 14,
              alignSelf: "start",
            }}
          >
            <div>
              <div
                style={{
                  fontSize: 10,
                  color: "#8b93ff",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  fontWeight: 700,
                }}
              >
                Roundtable
              </div>
              <p style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.7, margin: "8px 0 0" }}>
                Launched from Workstation. After your kickoff, the room should continue on its own,
                keep one active speaker at a time, and only stop when it reaches a recommendation,
                blocker, or approval point.
              </p>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr 1fr",
                gap: 8,
                padding: 4,
                borderRadius: 12,
                backgroundColor: "rgba(10,17,32,0.72)",
                border: "1px solid rgba(125,211,252,0.12)",
              }}
            >
              {(["current", "tasks", "meetings"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => {
                    setSidebarTab(tab)
                    if (tab === "tasks") void reloadRoomTasks()
                  }}
                  style={{
                    borderRadius: 9,
                    border: sidebarTab === tab ? "1px solid rgba(125,211,252,0.3)" : "1px solid transparent",
                    backgroundColor: sidebarTab === tab ? "rgba(59,130,246,0.16)" : "transparent",
                    color: sidebarTab === tab ? "#e2e8f0" : "#94a3b8",
                    padding: "9px 6px",
                    fontSize: 10,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  {tab}
                </button>
              ))}
            </div>

            {sidebarTab === "current" ? (
              <>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr 1fr",
                    gap: 8,
                  }}
                >
                  <button
                    type="button"
                    onClick={handleStartFreshMeeting}
                    disabled={Boolean(meetingActionId) || seatedParticipants.length < 2}
                    style={{
                      borderRadius: 10,
                      border: "1px solid rgba(125,211,252,0.2)",
                      backgroundColor: "rgba(14,116,144,0.18)",
                      color: "#bae6fd",
                      padding: "10px 12px",
                      fontSize: 10,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      fontWeight: 700,
                      cursor: meetingActionId ? "not-allowed" : "pointer",
                      opacity: meetingActionId || seatedParticipants.length < 2 ? 0.5 : 1,
                    }}
                  >
                    {meetingActionId === "new" ? "Starting…" : "New"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleEndMeeting(roomId)}
                    disabled={Boolean(meetingActionId)}
                    style={{
                      borderRadius: 10,
                      border: "1px solid rgba(250,204,21,0.2)",
                      backgroundColor: "rgba(161,98,7,0.18)",
                      color: "#fde68a",
                      padding: "10px 12px",
                      fontSize: 10,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      fontWeight: 700,
                      cursor: meetingActionId ? "not-allowed" : "pointer",
                      opacity: meetingActionId ? 0.5 : 1,
                    }}
                  >
                    {meetingActionId === `end:${roomId}` ? "Ending…" : "End"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDeleteMeeting(roomId)}
                    disabled={Boolean(meetingActionId)}
                    style={{
                      borderRadius: 10,
                      border: "1px solid rgba(248,113,113,0.22)",
                      backgroundColor: "rgba(127,29,29,0.18)",
                      color: "#fecaca",
                      padding: "10px 12px",
                      fontSize: 10,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      fontWeight: 700,
                      cursor: meetingActionId ? "not-allowed" : "pointer",
                      opacity: meetingActionId ? 0.5 : 1,
                    }}
                  >
                    {meetingActionId === `delete:${roomId}` ? "Deleting…" : "Delete"}
                  </button>
                </div>

                <div
                  style={{
                    border: "1px solid rgba(125,211,252,0.14)",
                    borderRadius: 12,
                    padding: "12px 14px",
                    backgroundColor: "rgba(10,17,32,0.72)",
                  }}
                >
                  <div
                    style={{
                      fontSize: 10,
                      color: "#cbd5f5",
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      fontWeight: 700,
                      marginBottom: 10,
                    }}
                  >
                    Seated participants
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {seatedParticipants.map((seat) => (
                      <div
                        key={seat.stationId}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 10,
                          border: `1px solid ${seat.accentHex}22`,
                          borderRadius: 10,
                          padding: "9px 10px",
                          backgroundColor: `${seat.accentHex}10`,
                        }}
                      >
                        <span
                          style={{
                            width: 10,
                            height: 10,
                            borderRadius: "50%",
                            backgroundColor: seat.accentHex,
                            boxShadow: `0 0 10px ${seat.accentHex}55`,
                            flexShrink: 0,
                          }}
                        />
                        <div style={{ minWidth: 0 }}>
                          <div
                            style={{
                              fontSize: 11,
                              color: "#e2e8f0",
                              fontWeight: 700,
                              letterSpacing: "0.04em",
                              textTransform: "uppercase",
                            }}
                          >
                            Chair {seat.seatIndex + 1}: {seat.label}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : sidebarTab === "tasks" ? (
              <div
                style={{
                  border: "1px solid rgba(125,211,252,0.14)",
                  borderRadius: 12,
                  padding: "12px 14px",
                  backgroundColor: "rgba(10,17,32,0.72)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div style={{ fontSize: 10, color: "#cbd5f5", letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 700 }}>
                  Guardian Tasks
                </div>
                {roomTasks.length === 0 ? (
                  <p style={{ fontSize: 11, color: "#4b5563", margin: 0, lineHeight: 1.6 }}>
                    No Task Guardian jobs in this room yet. Create them via Controls → Task Guardian.
                  </p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {roomTasks.map((task) => {
                      const statusColor =
                        task.last_status === "success" ? "#4ade80"
                        : task.last_status === "failed" ? "#f87171"
                        : task.last_status === "running" ? "#fbbf24"
                        : "#4b5563"
                      return (
                        <div
                          key={task.id}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            padding: "8px 10px",
                            backgroundColor: "rgba(7,13,28,0.6)",
                            border: "1px solid rgba(125,211,252,0.08)",
                            borderRadius: 8,
                          }}
                        >
                          <span style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: statusColor, flexShrink: 0 }} />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 11, fontWeight: 700, color: "#cbd5e1", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                              {task.name}
                            </div>
                            <div style={{ fontSize: 9, color: "#4b5563", marginTop: 1 }}>
                              {task.tool_name}{task.last_run_at ? ` · ${new Date(task.last_run_at).toLocaleDateString()}` : ""}
                            </div>
                          </div>
                          <button
                            type="button"
                            disabled={runningTaskId === task.id}
                            onClick={async () => {
                              setRunningTaskId(task.id)
                              try {
                                await apiFetch(`/api/v1/chat/rooms/${roomId}/guardian/tasks/${task.id}/run`, {
                                  method: "POST",
                                  credentials: "include",
                                })
                                await reloadRoomTasks()
                              } finally {
                                setRunningTaskId(null)
                              }
                            }}
                            style={{
                              background: "none",
                              border: "1px solid rgba(125,211,252,0.2)",
                              borderRadius: 4,
                              cursor: runningTaskId === task.id ? "not-allowed" : "pointer",
                              color: "#bae6fd",
                              fontSize: 9,
                              padding: "3px 7px",
                              letterSpacing: "0.06em",
                              textTransform: "uppercase",
                              flexShrink: 0,
                            }}
                          >
                            {runningTaskId === task.id ? "…" : "Run"}
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            ) : (
              <div
                style={{
                  border: "1px solid rgba(125,211,252,0.14)",
                  borderRadius: 12,
                  padding: "12px 14px",
                  backgroundColor: "rgba(10,17,32,0.72)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                  }}
                >
                  <div
                    style={{
                      fontSize: 10,
                      color: "#cbd5f5",
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      fontWeight: 700,
                    }}
                  >
                    Ongoing meetings
                  </div>
                  <button
                    type="button"
                    onClick={handleStartFreshMeeting}
                    disabled={Boolean(meetingActionId) || seatedParticipants.length < 2}
                    style={{
                      borderRadius: 8,
                      border: "1px solid rgba(125,211,252,0.2)",
                      backgroundColor: "rgba(14,116,144,0.18)",
                      color: "#bae6fd",
                      padding: "7px 10px",
                      fontSize: 10,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      fontWeight: 700,
                      cursor: meetingActionId ? "not-allowed" : "pointer",
                      opacity: meetingActionId || seatedParticipants.length < 2 ? 0.5 : 1,
                    }}
                  >
                    New
                  </button>
                </div>
                {meetingRooms.length === 0 ? (
                  <div style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6 }}>
                    No active meetings. Start a fresh Roundtable instance from here or from Workstation.
                  </div>
                ) : (
                  meetingRooms.map((meeting) => (
                    <div
                      key={meeting.id}
                      style={{
                        border: meeting.id === roomId ? "1px solid rgba(125,211,252,0.28)" : "1px solid rgba(99,102,241,0.16)",
                        borderRadius: 10,
                        padding: "10px 11px",
                        backgroundColor: meeting.id === roomId ? "rgba(14,116,144,0.12)" : "rgba(7,13,28,0.58)",
                        display: "flex",
                        flexDirection: "column",
                        gap: 8,
                      }}
                    >
                      <div>
                        <div style={{ fontSize: 11, color: "#e2e8f0", fontWeight: 700 }}>
                          {meeting.name}
                        </div>
                        <div style={{ fontSize: 10, color: "#64748b", marginTop: 4 }}>
                          Updated {new Date(meeting.updated_at || meeting.created_at).toLocaleString()}
                        </div>
                        {meeting.meta?.seats?.length ? (
                          <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 6, lineHeight: 1.5 }}>
                            {meeting.meta.seats.map((seat) => seat.label).join(" • ")}
                          </div>
                        ) : null}
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                        <button
                          type="button"
                          onClick={() => navigate({ to: "/meeting/$roomId", params: { roomId: meeting.id } })}
                          style={{
                            borderRadius: 8,
                            border: "1px solid rgba(125,211,252,0.18)",
                            backgroundColor: "rgba(14,116,144,0.16)",
                            color: "#bae6fd",
                            padding: "8px 9px",
                            fontSize: 10,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            fontWeight: 700,
                            cursor: "pointer",
                          }}
                        >
                          Open
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleEndMeeting(meeting.id)}
                          disabled={Boolean(meetingActionId)}
                          style={{
                            borderRadius: 8,
                            border: "1px solid rgba(250,204,21,0.2)",
                            backgroundColor: "rgba(161,98,7,0.18)",
                            color: "#fde68a",
                            padding: "8px 9px",
                            fontSize: 10,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            fontWeight: 700,
                            cursor: meetingActionId ? "not-allowed" : "pointer",
                            opacity: meetingActionId ? 0.5 : 1,
                          }}
                        >
                          {meetingActionId === `end:${meeting.id}` ? "Ending…" : "End"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDeleteMeeting(meeting.id)}
                          disabled={Boolean(meetingActionId)}
                          style={{
                            borderRadius: 8,
                            border: "1px solid rgba(248,113,113,0.22)",
                            backgroundColor: "rgba(127,29,29,0.18)",
                            color: "#fecaca",
                            padding: "8px 9px",
                            fontSize: 10,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            fontWeight: 700,
                            cursor: meetingActionId ? "not-allowed" : "pointer",
                            opacity: meetingActionId ? 0.5 : 1,
                          }}
                        >
                          {meetingActionId === `delete:${meeting.id}` ? "Deleting…" : "Delete"}
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            <button
              type="button"
              onClick={() => navigate({ to: "/workstation" })}
              style={{
                border: "1px solid rgba(99,102,241,0.16)",
                borderRadius: 10,
                backgroundColor: "rgba(7, 13, 28, 0.72)",
                color: "#cbd5f5",
                padding: "10px 12px",
                cursor: "pointer",
                fontSize: 11,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                fontWeight: 700,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
              }}
            >
              <Users size={14} />
              Back to Workstation
            </button>

            {sidebarTab === "current" && (
              <div
                style={{
                  borderTop: "1px solid rgba(99,102,241,0.16)",
                  paddingTop: 12,
                  marginTop: 4,
                }}
              >
                <button
                  type="button"
                  onClick={handleGenerateNotes}
                  disabled={generatingNotes}
                  style={{
                    width: "100%",
                    borderRadius: 8,
                    border: "1px solid rgba(99,102,241,0.3)",
                    backgroundColor: "rgba(49,46,129,0.2)",
                    padding: "8px 12px",
                    fontSize: 11,
                    color: "#a5b4fc",
                    cursor: generatingNotes ? "not-allowed" : "pointer",
                    opacity: generatingNotes ? 0.5 : 1,
                    transition: "background 0.15s",
                    letterSpacing: "0.06em",
                  }}
                >
                  {generatingNotes ? "Generating notes…" : "Generate Meeting Notes"}
                </button>
                {latestArtifact && (
                  <div
                    style={{
                      marginTop: 10,
                      borderRadius: 8,
                      border: "1px solid rgba(99,102,241,0.16)",
                      backgroundColor: "rgba(7,13,28,0.6)",
                      padding: 10,
                    }}
                  >
                    <p
                      style={{
                        marginBottom: 6,
                        fontSize: 9,
                        fontWeight: 700,
                        letterSpacing: "0.1em",
                        textTransform: "uppercase",
                        color: "#64748b",
                      }}
                    >
                      Meeting Notes · {new Date(latestArtifact.created_at).toLocaleTimeString()}
                    </p>
                    <pre
                      style={{
                        maxHeight: 256,
                        overflowY: "auto",
                        whiteSpace: "pre-wrap",
                        fontSize: 11,
                        color: "#cbd5e1",
                        lineHeight: 1.6,
                        margin: 0,
                        fontFamily: "inherit",
                      }}
                    >
                      {latestArtifact.content_markdown}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </aside>

          <section
            style={{
              border: "1px solid rgba(99,102,241,0.16)",
              borderRadius: 18,
              backgroundColor: "rgba(7, 13, 28, 0.68)",
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
            }}
          >
            <div
              style={{
                padding: "14px 16px",
                borderBottom: "1px solid rgba(99,102,241,0.12)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#e2e8f0" }}>
                  {room?.name ?? "Roundtable"}
                </div>
                <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>
                  Autonomous meeting mode is active. The room keeps working until it reaches a stopping point.
                </div>
              </div>
              <button
                type="button"
                onClick={() => setInfoOpen(true)}
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: 999,
                  border: "1px solid rgba(99,102,241,0.16)",
                  backgroundColor: "rgba(7, 13, 28, 0.72)",
                  color: "#cbd5f5",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
                aria-label="Meeting room info"
              >
                <Info size={16} />
              </button>
            </div>

            {loading ? (
              <div className="flex flex-1 items-center justify-center">
                <Loader2 className="size-8 animate-spin text-slate-500" />
              </div>
            ) : (
              <>
                <ChatWindow
                  messages={messages}
                  currentUser={currentUser}
                  isLoading={false}
                  typingUsers={[]}
                  className="flex-1"
                />
                {streamError && (
                  <div
                    style={{
                      padding: "8px 16px",
                      margin: "0 0 2px",
                      fontSize: 12,
                      color: "#f87171",
                      borderTop: "1px solid rgba(248,113,113,0.20)",
                      background: "rgba(248,113,113,0.06)",
                    }}
                  >
                    ⚠ {streamError}
                  </div>
                )}
                {streamingToken && (
                  <div
                    style={{
                      padding: "8px 16px",
                      margin: "0 0 2px",
                      fontSize: 13,
                      color: "#a5b4fc",
                      borderTop: "1px solid rgba(99,102,241,0.10)",
                      whiteSpace: "pre-wrap",
                      lineHeight: 1.6,
                      fontStyle: "italic",
                    }}
                  >
                    {streamingAgent && (
                      <span style={{ fontWeight: 700, fontStyle: "normal", marginRight: 8, fontSize: 11, color: "#7dd3fc" }}>
                        {streamingAgent}
                      </span>
                    )}
                    {streamingToken}
                    <span style={{ animation: "blink 1s step-end infinite", opacity: 0.7 }}>▌</span>
                  </div>
                )}
                <div
                  style={{
                    padding: "4px 16px 2px",
                    fontSize: 10,
                    color: "#475569",
                    letterSpacing: "0.05em",
                  }}
                >
                  {sending
                    ? "Meeting is running. Send a new message to interrupt, redirect, or add owner input."
                    : seatedParticipants.length > 0
                    ? `Kick off the topic once, or call on someone directly with ${seatedParticipants.map((s) => `@${s.label.toLowerCase().replace(/\s+/g, "")}`).join("  ")}`
                    : "Type your kickoff and the roundtable will continue autonomously."}
                </div>
                <ChatInput
                  value={inputValue}
                  onChange={setInputValue}
                  onSubmit={handleSendMessage}
                  isLoading={false}
                  placeholder={sending ? "Interrupt or redirect the meeting…" : "Kick off the meeting objective…"}
                />
              </>
            )}
          </section>
        </main>
      </div>

      <SparkbotSurfaceInfoDialog
        open={infoOpen}
        title="Roundtable Meeting Room"
        subtitle="This room was launched from Workstation as the live group chat version of the central table."
        bullets={[
          "Roundtable is the live room spawned from the eight-seat table in Workstation.",
          "Autonomous meeting mode keeps the room moving after your kickoff while preserving one active speaker at a time.",
          "You are the owner and approver. Jump in whenever you want; the room should only stop for approval, missing input, blockers, or a clear recommendation.",
          "Use Workstation to reseat desks, change the table, or launch again after reconfiguring chairs.",
          "Chat remains the everyday home. This room is the focused collaboration surface.",
        ]}
        onClose={() => setInfoOpen(false)}
      />
    </>
  )
}
