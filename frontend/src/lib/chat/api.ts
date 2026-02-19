// Chat API client functions

import { request as __request } from "@/client/core/request"
import { OpenAPI } from "@/client"
import type { CancelablePromise } from "@/client/core/CancelablePromise"
import type { Room, Message, SendMessageRequest, CreateRoomRequest, User } from "./types"

// Generate proper types from your backend API
// These are placeholder interfaces - replace with actual API types

interface RoomsResponse {
  data: Room[]
  total: number
}

interface MessagesResponse {
  data: Message[]
  total: number
}

interface MessageResponse {
  data: Message
}

interface RoomResponse {
  data: Room
}

interface UsersResponse {
  data: User[]
}

class ChatApiClient {
  private baseUrl = "/api/v1/chat"

  // Rooms
  getRooms(skip = 0, limit = 50): CancelablePromise<RoomsResponse> {
    return __request(OpenAPI, {
      method: "GET",
      url: `${this.baseUrl}/rooms`,
      query: { skip, limit },
    })
  }

  getRoom(roomId: string): CancelablePromise<RoomResponse> {
    return __request(OpenAPI, {
      method: "GET",
      url: `${this.baseUrl}/rooms/${roomId}`,
    })
  }

  createRoom(data: CreateRoomRequest): CancelablePromise<RoomResponse> {
    return __request(OpenAPI, {
      method: "POST",
      url: `${this.baseUrl}/rooms`,
      body: data,
      mediaType: "application/json",
    })
  }

  deleteRoom(roomId: string): CancelablePromise<void> {
    return __request(OpenAPI, {
      method: "DELETE",
      url: `${this.baseUrl}/rooms/${roomId}`,
    })
  }

  leaveRoom(roomId: string): CancelablePromise<void> {
    return __request(OpenAPI, {
      method: "POST",
      url: `${this.baseUrl}/rooms/${roomId}/leave`,
    })
  }

  // Messages
  getMessages(roomId: string, skip = 0, limit = 50): CancelablePromise<MessagesResponse> {
    return __request(OpenAPI, {
      method: "GET",
      url: `${this.baseUrl}/rooms/${roomId}/messages`,
      query: { skip, limit },
    })
  }

  sendMessage(data: SendMessageRequest): CancelablePromise<MessageResponse> {
    return __request(OpenAPI, {
      method: "POST",
      url: `${this.baseUrl}/rooms/${data.room_id}/messages`,
      body: { content: data.content, message_type: data.message_type },
      mediaType: "application/json",
    })
  }

  deleteMessage(roomId: string, messageId: string): CancelablePromise<void> {
    return __request(OpenAPI, {
      method: "DELETE",
      url: `${this.baseUrl}/rooms/${roomId}/messages/${messageId}`,
    })
  }

  // Users
  searchUsers(query: string): CancelablePromise<UsersResponse> {
    return __request(OpenAPI, {
      method: "GET",
      url: `${this.baseUrl}/users/search`,
      query: { q: query },
    })
  }

  getRoomParticipants(roomId: string): CancelablePromise<UsersResponse> {
    return __request(OpenAPI, {
      method: "GET",
      url: `${this.baseUrl}/rooms/${roomId}/participants`,
    })
  }
}

export const chatApi = new ChatApiClient()
