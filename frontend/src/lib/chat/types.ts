// Chat types for the chat UI

export interface User {
  id: string
  username: string
  display_name?: string
  avatar_url?: string
  is_online?: boolean
  last_seen?: string
}

export interface Room {
  id: string
  name: string
  description?: string
  type: "direct" | "group" | "public"
  created_by: string
  created_at: string
  updated_at: string
  unread_count?: number
  last_message?: Message
  participants?: User[]
}

export interface Message {
  id: string
  room_id: string
  user_id: string
  content: string
  message_type: "text" | "image" | "file" | "system"
  created_at: string
  updated_at?: string
  is_edited?: boolean
  is_deleted?: boolean
  user?: User
  reactions?: Reaction[]
}

export interface Reaction {
  emoji: string
  user_id: string
  created_at: string
}

export interface SendMessageRequest {
  room_id: string
  content: string
  message_type?: "text" | "image" | "file"
}

export interface CreateRoomRequest {
  name: string
  description?: string
  type: "direct" | "group" | "public"
  participant_ids?: string[]
}

export interface ChatState {
  rooms: Room[]
  currentRoom: Room | null
  messages: Message[]
  isLoading: boolean
  error: string | null
  isConnected: boolean
}

export interface WebSocketMessage {
  type: "message" | "reaction" | "typing" | "user_joined" | "user_left" | "room_updated" | "join_room" | "leave_room" | "remove_reaction"
  payload: unknown
}
