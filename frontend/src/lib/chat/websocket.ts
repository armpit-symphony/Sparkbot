// WebSocket client for real-time chat

import type { Message, WebSocketMessage } from "./types"

type WebSocketHandler = (data: WebSocketMessage) => void

interface WebSocketConfig {
  url?: string
  autoReconnect?: boolean
  reconnectInterval?: number
  onMessage?: WebSocketHandler
  onConnect?: () => void
  onDisconnect?: () => void
  onError?: (error: Event) => void
  onTyping?: (data: { room_id: string; user_id: string; is_typing: boolean }) => void
}

class ChatWebSocket {
  private ws: WebSocket | null = null
  private config: Required<WebSocketConfig>
  private reconnectAttempts = 0
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  private messageHandlers: Set<WebSocketHandler> = new Set()
  private currentRoomId: string | null = null

  constructor(config: WebSocketConfig = {}) {
    this.config = {
      url: config.url || `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/api/v1/chat/ws`,
      autoReconnect: config.autoReconnect ?? true,
      reconnectInterval: config.reconnectInterval ?? 3000,
      onMessage: config.onMessage || (() => {}),
      onConnect: config.onConnect || (() => {}),
      onDisconnect: config.onDisconnect || (() => {}),
      onError: config.onError || (() => {}),
      onTyping: config.onTyping || (() => {}),
    }
  }

  connect(token: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return
    }

    const url = new URL(this.config.url)
    url.searchParams.set("token", token)

    this.ws = new WebSocket(url.toString())

    this.ws.onopen = () => {
      console.log("Chat WebSocket connected")
      this.reconnectAttempts = 0
      this.config.onConnect()

      // Rejoin current room if any
      if (this.currentRoomId) {
        this.joinRoom(this.currentRoomId)
      }
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketMessage

        // Handle typing events specially
        if (data.type === "typing") {
          const typingData = data.payload as { room_id: string; user_id: string; is_typing: boolean }
          this.config.onTyping(typingData)
          return
        }

        // Notify all handlers
        this.messageHandlers.forEach((handler) => handler(data))
        this.config.onMessage(data)
      } catch (error) {
        console.error("Failed to parse WebSocket message:", error)
      }
    }

    this.ws.onclose = () => {
      console.log("Chat WebSocket disconnected")
      this.config.onDisconnect()
      this.ws = null

      // Auto reconnect
      if (this.config.autoReconnect) {
        this.scheduleReconnect()
      }
    }

    this.ws.onerror = (error) => {
      console.error("Chat WebSocket error:", error)
      this.config.onError(error)
    }
  }

  disconnect(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  private scheduleReconnect(): void {
    if (!this.config.autoReconnect) return

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectAttempts++
      console.log(`Attempting to reconnect (${this.reconnectAttempts})...`)
      // Get token from localStorage
      const token = localStorage.getItem("access_token")
      if (token) {
        this.connect(token)
      }
    }, this.config.reconnectInterval)
  }

  joinRoom(roomId: string): void {
    this.send({ type: "join_room", payload: { room_id: roomId } })
    this.currentRoomId = roomId
  }

  leaveRoom(roomId: string): void {
    this.send({ type: "leave_room", payload: { room_id: roomId } })
    if (this.currentRoomId === roomId) {
      this.currentRoomId = null
    }
  }

  sendMessage(message: Omit<Message, "id" | "created_at" | "user">): void {
    this.send({ type: "message", payload: message })
  }

  sendTyping(roomId: string, isTyping: boolean): void {
    this.send({ type: "typing", payload: { room_id: roomId, is_typing: isTyping } })
  }

  sendReaction(roomId: string, messageId: string, emoji: string): void {
    this.send({ type: "reaction", payload: { room_id: roomId, message_id: messageId, emoji } })
  }

  removeReaction(roomId: string, messageId: string, emoji: string): void {
    this.send({ type: "remove_reaction", payload: { room_id: roomId, message_id: messageId, emoji } })
  }

  private send(data: WebSocketMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    } else {
      console.warn("WebSocket is not connected")
    }
  }

  addMessageHandler(handler: WebSocketHandler): () => void {
    this.messageHandlers.add(handler)
    return () => {
      this.messageHandlers.delete(handler)
    }
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

export const chatWebSocket = new ChatWebSocket()
