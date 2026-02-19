// Chat hooks for React components

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useState, useEffect } from "react"
import { chatApi } from "./api"
import { chatWebSocket } from "./websocket"
import type { Message, Room, SendMessageRequest, CreateRoomRequest } from "./types"

export function useRooms() {
  return useQuery({
    queryKey: ["chat", "rooms"],
    queryFn: async () => {
      console.log("[QUERY] rooms queryFn fired")
      const response = await chatApi.getRooms()
      console.log("[QUERY] rooms result:", response.data?.length, "items")
      return response.data
    },
    retry: 0,
    staleTime: 0,
    gcTime: 0,
  })
}

export function useRoom(roomId: string | null) {
  return useQuery({
    queryKey: ["chat", "room", roomId],
    queryFn: async () => {
      if (!roomId) return null
      const response = await chatApi.getRoom(roomId)
      return response.data
    },
    enabled: !!roomId,
  })
}

export function useMessages(roomId: string | null) {
  return useQuery({
    queryKey: ["chat", "messages", roomId],
    queryFn: async () => {
      if (!roomId) return []
      const response = await chatApi.getMessages(roomId)
      return response.data
    },
    enabled: !!roomId,
    staleTime: 1000, // Consider messages fresh for 1 second
  })
}

export function useSendMessage() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: SendMessageRequest) => chatApi.sendMessage(data),
    onSuccess: (response) => {
      const message = response.data
      queryClient.setQueryData(
        ["chat", "messages", message.room_id],
        (old: Message[] = []) => [...old, message]
      )
    },
  })
}

export function useDeleteMessage() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ roomId, messageId }: { roomId: string; messageId: string }) =>
      chatApi.deleteMessage(roomId, messageId),
    onSuccess: (_, { roomId, messageId }) => {
      queryClient.setQueryData(
        ["chat", "messages", roomId],
        (old: Message[] = []) =>
          old.map((msg) =>
            msg.id === messageId
              ? { ...msg, is_deleted: true, content: "This message has been deleted" }
              : msg
          )
      )
    },
  })
}

export function useCreateRoom() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: CreateRoomRequest) => chatApi.createRoom(data),
    onSuccess: (response) => {
      const room = response.data
      queryClient.setQueryData(["chat", "rooms"], (old: Room[] = []) => [...old, room])
    },
  })
}

export function useLeaveRoom() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (roomId: string) => chatApi.leaveRoom(roomId),
    onSuccess: (_, roomId) => {
      queryClient.setQueryData(["chat", "rooms"], (old: Room[] = []) =>
        old.filter((room) => room.id !== roomId)
      )
    },
  })
}

export function useChatWebSocket() {
  return {
    connect: (token: string) => chatWebSocket.connect(token),
    disconnect: () => chatWebSocket.disconnect(),
    joinRoom: (roomId: string) => chatWebSocket.joinRoom(roomId),
    leaveRoom: (roomId: string) => chatWebSocket.leaveRoom(roomId),
    sendTyping: (roomId: string, isTyping: boolean) =>
      chatWebSocket.sendTyping(roomId, isTyping),
    addMessageHandler: (handler: Parameters<typeof chatWebSocket.addMessageHandler>[0]) =>
      chatWebSocket.addMessageHandler(handler),
    isConnected: chatWebSocket.isConnected,
  }
}

export function useTypingUsers(roomId: string | null) {
  const [typingUsers, setTypingUsers] = useState<
    Map<string, { userId: string; username: string }>
  >(new Map())

  useEffect(() => {
    if (!roomId) return

    const cleanup = chatWebSocket.addMessageHandler((data) => {
      if (data.type === "typing") {
        const typingData = data.payload as {
          room_id: string
          user_id: string
          username: string
          is_typing: boolean
        }
        if (typingData.room_id === roomId) {
          setTypingUsers((prev) => {
            const next = new Map(prev)
            if (typingData.is_typing) {
              next.set(typingData.user_id, {
                userId: typingData.user_id,
                username: typingData.username,
              })
            } else {
              next.delete(typingData.user_id)
            }
            return next
          })
        }
      }
    })

    return cleanup
  }, [roomId])

  return Array.from(typingUsers.values())
}
