// ChatPage - Main chat page component

import { useState, useCallback, useEffect, useMemo } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { ChatLayout } from "@/components/chat/ChatLayout"
import {
  useRooms,
  useMessages,
  useDeleteMessage,
  useChatWebSocket,
  useTypingUsers,
} from "@/lib/chat/hooks"
import type { Room, Message } from "@/lib/chat/types"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/chat")({
  component: ChatPage,
})

interface BootStatus {
  status?: number
  body?: string
}

function ChatPage() {
  const { user: currentUser } = useAuth()
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null)
  const [bootStatus, setBootStatus] = useState<BootStatus | null>(null)
  const [stuck, setStuck] = useState(false)
  const [mounted, setMounted] = useState(false)
  const [tapLog, setTapLog] = useState<string[]>([])
  const [joinOpen, setJoinOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [sendStatus, setSendStatus] = useState<string>("")
  const [bootDebug] = useState<{status?: number; body?: string; err?: string; nav?: string}>()

  const logTap = (msg: string) => {
    console.log("[TAP]", msg)
    setTapLog((p) => [`${new Date().toISOString().slice(11,19)} ${msg}`, ...p].slice(0, 8))
  }

  // Debug modal - simple fixed overlay with actual API call
  const DebugModal = ({ open, onClose, title }: { open: boolean; onClose: () => void; title: string }) => {
    const [roomName, setRoomName] = useState("")
    const [actionStatus, setActionStatus] = useState("idle")
    
    const onJoin = async () => {
      setActionStatus("clicked")
      console.log("[UI] Join clicked")
      try {
        const token = localStorage.getItem("access_token")
        const res = await fetch("/api/v1/chat/rooms", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ name: roomName.trim() }),
        })
        const text = await res.text()
        setActionStatus(`status=${res.status} body=${text.slice(0,120)}`)
        console.log("[UI] Join result", res.status, text)
        
        // On success, close modal and trigger room list refresh
        if (res.ok) {
          try {
            const room = JSON.parse(text)
            setActionStatus(`status=${res.status} room.id=${room.id}`)
            // Close modal
            onClose()
            // Force refresh by updating bootStatus to trigger re-fetch
            setBootStatus(null)
            // Small delay then re-boot to refresh list
            setTimeout(() => {
              const token2 = localStorage.getItem("access_token")
              fetch("/api/v1/chat/rooms", {
                headers: { Authorization: `Bearer ${token2}` }
              }).then(r => r.json()).then(data => {
                console.log("[UI] Refreshed rooms:", data)
                setBootStatus({ status: 200, body: JSON.stringify(data) })
              })
            }, 200)
          } catch {}
        }
      } catch (e: any) {
        setActionStatus(`error=${e?.message || String(e)}`)
        console.log("[UI] Join error", e)
      }
    }
    
    if (!open) return null
    return (
      <div style={{ 
        position: "fixed", 
        inset: 0, 
        zIndex: 999999, 
        background: "rgba(0,0,0,0.65)", 
        display: "flex", 
        alignItems: "center", 
        justifyContent: "center", 
        padding: 16,
      }}>
        <div style={{ 
          width: "min(92vw, 420px)", 
          background: "#111", 
          border: "1px solid #333", 
          borderRadius: 12, 
          padding: 16, 
          maxHeight: "80vh", 
          overflow: "auto",
          color: "white",
        }}>
          <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom: 12}}>
            <b>{title}</b>
            <button 
              onClick={onClose}
              style={{ background: "#333", border: "none", color: "white", padding: "8px 16px", borderRadius: 6 }}
            >
              Close
            </button>
          </div>
          <input 
            placeholder="room name" 
            value={roomName}
            onChange={(e) => setRoomName(e.target.value)}
            autoCapitalize="none"
            autoCorrect="off"
            style={{
              width:"100%", 
              padding: 10, 
              marginBottom: 8, 
              color: "#fff !important", 
              background: "transparent !important",
              caretColor: "#fff !important",
              WebkitTextFillColor: "#fff !important",
              opacity: 1,
            }} 
          />
          <button 
            onClick={onJoin}
            style={{width:"100%", padding: 10, background: "#2563eb", border: "none", color: "white", borderRadius: 6}}
          >
            {title}
          </button>
          <pre style={{whiteSpace:"pre-wrap", fontSize:11, marginTop: 12, color: actionStatus.startsWith("error") ? "#f87171" : "#4ade80"}}>
{actionStatus}
          </pre>
        </div>
      </div>
    )
  }

  // BOOTSTRAP FETCH: Run FIRST, unconditionally, before ANY conditionals
  useEffect(() => {
    console.log("[BOOT] Effect mounted at", Date.now())
    setMounted(true)
    
    async function doBoot() {
      try {
        // Read token directly from localStorage - no module race conditions
        const token = localStorage.getItem("access_token")
        console.log("[BOOT] Token from localStorage:", token?.substring?.(0, 30))
        
        if (!token) {
          console.log("[BOOT] No token in localStorage")
          return
        }
        
        console.log("[BOOT] Fetching /api/v1/chat/rooms...")
        const res = await fetch("/api/v1/chat/rooms", {
          headers: {
            "Authorization": `Bearer ${token}`,
          }
        })
        const text = await res.text()
        console.log("[BOOT] rooms status:", res.status)
        setBootStatus({ status: res.status, body: text.slice(0, 500) })
        
        // Auto-create Sparkbot DM room if none exists
        if (res.ok) {
          try {
            const roomsData = JSON.parse(text)
            const hasSparkbotRoom = roomsData.items?.some((r: any) => 
              r.name?.toLowerCase().includes("sparkbot")
            )
            
            if (!hasSparkbotRoom) {
              console.log("[BOOT] Creating Sparkbot DM room...")
              const createRes = await fetch("/api/v1/chat/rooms", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "Authorization": `Bearer ${token}`,
                },
                body: JSON.stringify({ name: "Sparkbot DM" }),
              })
              console.log("[BOOT] Created room:", createRes.status)
            }
          } catch (e) {
            console.log("[BOOT] Auto-create check failed:", e)
          }
        }
      } catch (e: any) {
        console.log("[BOOT] error:", e?.message || e)
        setBootStatus({ status: -1, body: String(e) })
      }
    }
    
    // Small delay to ensure localStorage is set
    setTimeout(doBoot, 100)
  }, []) // Empty deps - run once on mount

  // Stuck detection - fail-fast after 3 seconds
  useEffect(() => {
    console.log("[CHATPAGE] Stuck timer started")
    const timer = setTimeout(() => {
      console.log("[CHATPAGE] Still loading after 3s - marking as stuck")
      setStuck(true)
    }, 3000)
    return () => clearTimeout(timer)
  }, [])

  // Chat queries and mutations
  const { data: roomsQueryData } = useRooms()
  
  // Parse boot fetch response as fallback
  const bootRooms = useMemo(() => {
    if (!bootStatus?.body) return []
    try {
      const parsed = JSON.parse(bootStatus.body)
      console.log("[PARSE] bootStatus.body:", bootStatus.body.slice(0, 200))
      console.log("[PARSE] parsed:", parsed)
      // API returns array directly, not {items: [...]}
      const rooms = Array.isArray(parsed) ? parsed : (parsed.items || [])
      console.log("[PARSE] rooms:", rooms.length)
      return rooms
    } catch (e) {
      console.log("[PARSE] error:", e)
      return []
    }
  }, [bootStatus])
  
  // Auto-select Sparkbot DM room on first load - try ALL sources
  useEffect(() => {
    console.log("[AUTO-SELECT] Running, bootRooms:", bootRooms?.length, "selectedRoom:", selectedRoom?.id)
    const sparkbotRoomId = localStorage.getItem("sparkbot_room_id")
    console.log("[AUTO-SELECT] sparkbot_room_id from localStorage:", sparkbotRoomId)
    
    // If we have a selected room, we're good
    if (selectedRoom) {
      console.log("[AUTO-SELECT] Already have selectedRoom:", selectedRoom.name)
      return
    }
    
    // Try to find room in bootRooms first
    if (bootRooms && bootRooms.length > 0) {
      // First try by stored room ID
      let room = sparkbotRoomId ? bootRooms.find((r: any) => r.id === sparkbotRoomId) : null
      console.log("[AUTO-SELECT] Trying by roomId:", sparkbotRoomId, "found:", !!room)
      
      // Fallback to finding by name
      if (!room) {
        room = bootRooms.find((r: any) => r.name?.toLowerCase().includes("sparkbot"))
        console.log("[AUTO-SELECT] Trying by name, found:", !!room)
      }
      
      if (room) {
        console.log("[AUTO-SELECT] Auto-selecting room:", room.name, room.id)
        setSelectedRoom(room as Room)
        return
      }
    }
    
    // If we have a stored room ID but no bootRooms yet, wait for bootRooms
    // But if we have NO rooms at all, still try to set from localStorage
    if (sparkbotRoomId && (!bootRooms || bootRooms.length === 0)) {
      console.log("[AUTO-SELECT] No bootRooms yet, will wait...")
    }
  }, [bootRooms])
  
  // Use TanStack data, fallback to boot rooms
  const rooms = roomsQueryData || bootRooms || []
  console.log("[CHATPAGE] rooms:", roomsQueryData?.length, "boot:", bootRooms?.length, "final:", rooms.length)
  
  const { data: messages } = useMessages(selectedRoom?.id || null)
  const deleteMessageMutation = useDeleteMessage()

  // WebSocket
  const ws = useChatWebSocket()

  // Typing users
  const typingUsers = useTypingUsers(selectedRoom?.id || null)

  // Connect to WebSocket on mount
  useEffect(() => {
    const token = localStorage.getItem("access_token")
    console.log("[CHATPAGE] WS connect token present:", !!token)
    if (token) {
      ws.connect(token)
    }

    return () => {
      ws.disconnect()
    }
  }, [])

  // Join room when selected
  useEffect(() => {
    if (selectedRoom?.id) {
      ws.joinRoom(selectedRoom.id)
    }

    return () => {
      if (selectedRoom?.id) {
        ws.leaveRoom(selectedRoom.id)
      }
    }
  }, [selectedRoom?.id])

  const handleSelectRoom = useCallback(
    (room: Room) => {
      // Leave previous room
      if (selectedRoom?.id) {
        ws.leaveRoom(selectedRoom.id)
      }

      setSelectedRoom(room)

      // Join new room
      ws.joinRoom(room.id)
    },
    [selectedRoom, ws]
  )

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (!selectedRoom || !content.trim()) return

      // Use localStorage directly to avoid module race conditions
      const token = localStorage.getItem("access_token")
      console.log("[SEND] Sending message, token:", token?.substring(0, 20))
      setSendStatus("sending...")
      
      try {
        const res = await fetch(`/api/v1/chat/rooms/${selectedRoom.id}/messages`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
          body: JSON.stringify({ content: content.trim() }),
        })
        
        const text = await res.text()
        console.log("[SEND] status:", res.status, "body:", text.slice(0, 200))
        setSendStatus(`status=${res.status} body=${text.slice(0,100)}`)
        
        if (!res.ok) {
          toast.error(`Failed: ${res.status}`)
        } else {
          // Clear status on success after delay
          setTimeout(() => setSendStatus(""), 3000)
        }
      } catch (e: any) {
        console.error("[SEND] error:", e)
        setSendStatus(`error: ${e?.message || String(e)}`)
        toast.error("Failed to send message")
      }
    },
    [selectedRoom]
  )

  const handleDeleteMessage = useCallback(
    (messageId: string) => {
      if (!selectedRoom) return

      deleteMessageMutation.mutate(
        { roomId: selectedRoom.id, messageId },
        {
          onError: () => {
            toast.error("Failed to delete message")
          },
        }
      )
    },
    [selectedRoom, deleteMessageMutation]
  )

  // Never show loading spinner if we have rooms - always render the chat UI
  // The rooms come from either TanStack query or bootStatus fallback
  const hasRooms = (rooms && rooms.length > 0) || (bootRooms && bootRooms.length > 0)
  
  // Debug info - show always
  const debugRooms = `ROOMS: ${rooms.length}, queryData: ${roomsQueryData?.length || 0}, bootRooms: ${bootRooms?.length || 0}`
  
  // Only show loading if absolutely no data yet
  if (!hasRooms && !bootStatus) {
    return (
      <div className="flex h-full flex-col items-center justify-center">
        <div className="absolute top-2 right-2 text-xs text-muted-foreground">
          BUILD: {import.meta.env?.VITE_BUILD_ID || Date.now().toString()}
        </div>
        <pre style={{fontSize: 11, opacity: 0.8, whiteSpace: "pre-wrap", maxWidth: "90%", textAlign: "center"}}>
{JSON.stringify(bootDebug, null, 2)}
{debugRooms}
        </pre>
        {hasRooms && (
          <button 
            onClick={() => {
              const room = bootRooms.find((r: any) => r.name?.toLowerCase().includes("sparkbot"))
              if (room) {
                setSelectedRoom(room as Room)
              }
            }}
            style={{ padding: "12px 24px", marginTop: 12, background: "#2563eb", color: "white", border: "none", borderRadius: 6 }}
          >
            Go to Sparkbot DM
          </button>
        )}
        <Loader2 className="mt-4 h-8 w-8 animate-spin text-muted-foreground" />
        {bootStatus && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50 p-8">
            <pre className="bg-black p-4 text-white text-xs whitespace-pre-wrap max-w-2xl overflow-auto">
BOOT status={(bootStatus as any).status}
{(bootStatus as any).body}
            </pre>
          </div>
        )}
        {stuck && !bootStatus && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50">
            <pre className="bg-black p-4 text-white text-xs whitespace-pre-wrap max-w-md">
mounted={mounted ? "true" : "false"}
localStorage has token: {localStorage.getItem("access_token") ? "yes" : "no"}
STUCK: rooms request never fired
            </pre>
          </div>
        )}
      </div>
    )
  }

  // Also show debug when rooms exist but empty
  const showEmptyDebug = rooms && rooms.length > 0 && !selectedRoom
  
  return (
    <>
      {showEmptyDebug && (
        <div className="absolute top-12 left-2 z-50 bg-black/80 p-2 rounded text-xs text-white">
          DEBUG: rooms={rooms.length} selectedRoom={(selectedRoom as any)?.id || 'none'}
          <br/>
          {JSON.stringify(bootDebug)}
        </div>
      )}
      <div 
        style={{ 
          position: "fixed", 
          bottom: 10, 
          left: 10, 
          right: 10, 
          zIndex: 999999, 
          fontSize: 12, 
          opacity: 0.9, 
          pointerEvents: "none", 
          background: "rgba(0,0,0,0.6)", 
          padding: 8, 
          borderRadius: 8, 
          whiteSpace: "pre-wrap",
          color: "white",
        }}
      >
        {tapLog.join("\n") || "tapLog: (empty)"}
        {sendStatus && `\n[SEND] ${sendStatus}`}
      </div>
      <ChatLayout
        rooms={rooms}
        currentRoom={selectedRoom}
        messages={(messages as Message[]) || []}
        currentUser={currentUser as any}
        onSelectRoom={handleSelectRoom}
        onSendMessage={handleSendMessage}
        onDeleteMessage={handleDeleteMessage}
        typingUsers={typingUsers}
        onJoinRoom={() => {
          logTap("CLICK Join Room")
          setJoinOpen(true)
          console.log("joinOpen set to true")
        }}
        onCreateRoom={() => {
          logTap("CLICK New Group")
          setCreateOpen(true)
          console.log("createOpen set to true")
        }}
      />
      <DebugModal open={joinOpen} onClose={() => setJoinOpen(false)} title="Join Room" />
      <DebugModal open={createOpen} onClose={() => setCreateOpen(false)} title="New Group" />
    </>
  )
}

export default ChatPage
