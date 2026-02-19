// Sparkbot DM Page - Direct message view

import { useState, useEffect, useCallback, useRef } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { Loader2 } from "lucide-react"

export const Route = createFileRoute("/dm")({
  component: SparkbotDmPage,
})

interface Message {
  id: string
  content: string
  created_at: string
  user_id: string
  username?: string
}

function SparkbotDmPage() {
  const [roomId, setRoomId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [inputValue, setInputValue] = useState("")
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // Initialize - call bootstrap and load messages
  useEffect(() => {
    async function init() {
      const token = localStorage.getItem("access_token")
      if (!token) {
        window.location.href = "/login"
        return
      }

      try {
        const bootstrapRes = await fetch("/api/v1/chat/users/bootstrap", {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`,
          },
        })

        if (!bootstrapRes.ok) {
          window.location.href = "/login"
          return
        }

        const boot = await bootstrapRes.json()
        setRoomId(boot.room_id)

        // Load messages
        const msgsRes = await fetch(`/api/v1/chat/rooms/${boot.room_id}/messages`, {
          headers: {
            "Authorization": `Bearer ${token}`,
          },
        })

        if (msgsRes.ok) {
          const msgsData = await msgsRes.json()
          const msgs = msgsData.messages || msgsData.items || (Array.isArray(msgsData) ? msgsData : [])
          setMessages(msgs)
        }
      } catch (e) {
        console.error("Init error:", e)
      } finally {
        setLoading(false)
      }
    }

    init()
  }, [])

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || !roomId || sending) return

    setSending(true)
    const token = localStorage.getItem("access_token")
    const url = `/api/v1/chat/rooms/${roomId}/messages`
    const payload = JSON.stringify({ content: inputValue.trim() })

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: payload,
      })

      if (res.ok) {
        const data = await res.json()
        // Handle {human: {...}, bot: {...}} response
        const humanMsg = data.human || data
        const botMsg = data.bot
        
        // Add human message
        setMessages(prev => [...prev, humanMsg])
        setInputValue("")
        
        // Add bot response if available
        if (botMsg) {
          setMessages(prev => [...prev, botMsg])
        }
      } else {
        console.error("Send failed:", res.status)
      }
    } catch (e) {
      console.error("Send error:", e)
    } finally {
      setSending(false)
    }
  }, [inputValue, roomId, sending])

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h1 className="text-lg font-semibold">Sparkbot DM</h1>
        <button 
          onClick={() => {
            localStorage.removeItem("access_token")
            window.location.href = "/login"
          }}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          Logout
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {messages.length === 0 ? (
          <p className="text-center text-muted-foreground">No messages yet. Say hello!</p>
        ) : (
          messages.map(msg => (
            <div key={msg.id} className="bg-muted p-3 rounded-lg">
              <p className="text-sm">{msg.content}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {msg.created_at ? new Date(msg.created_at).toLocaleTimeString() : ''}
              </p>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t p-4">
        <div className="flex gap-2">
          <input
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder="Type a message..."
            className="flex-1 border rounded-lg px-3 py-2"
            disabled={sending}
          />
          <button
            onClick={handleSend}
            disabled={sending || !inputValue.trim()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg disabled:opacity-50"
          >
            {sending ? "..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  )
}

export default SparkbotDmPage
