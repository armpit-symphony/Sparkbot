// ChatLayout component - main chat container

import { useState } from "react"
import { ArrowLeft, MoreVertical, Users } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Separator } from "@/components/ui/separator"
import { useIsMobile } from "@/hooks/useMobile"
import { cn } from "@/lib/utils"
import type { Room, User, Message } from "@/lib/chat/types"
import RoomList from "./RoomList"
import ChatWindow from "./ChatWindow"
import ChatInput from "./ChatInput"
import UserAvatar from "./UserAvatar"

interface ChatLayoutProps {
  rooms: Room[]
  currentRoom: Room | null
  messages: Message[]
  currentUser: User | null
  isLoadingMessages?: boolean
  onSelectRoom: (room: Room) => void
  onSendMessage: (content: string) => void
  onDeleteMessage?: (messageId: string) => void
  onLeaveRoom?: () => void
  onSettings?: () => void
  onBack?: () => void
  onJoinRoom?: () => void
  onCreateRoom?: () => void
  typingUsers?: Array<{ userId: string; username: string }>
  className?: string
}

export function ChatLayout({
  rooms,
  currentRoom,
  messages,
  currentUser,
  isLoadingMessages = false,
  onSelectRoom,
  onSendMessage,
  onDeleteMessage,
  onLeaveRoom,
  onSettings,
  onBack,
  onJoinRoom,
  onCreateRoom,
  typingUsers = [],
  className,
}: ChatLayoutProps) {
  const isMobile = useIsMobile()
  const [showRoomList, setShowRoomList] = useState(!currentRoom || !isMobile)
  const [inputValue, setInputValue] = useState("")

  const handleSelectRoom = (room: Room) => {
    onSelectRoom(room)
    setInputValue("")
    if (isMobile) {
      setShowRoomList(false)
    }
  }

  const handleSendMessage = (content: string) => {
    onSendMessage(content)
    setInputValue("")
  }

  const showChat = currentRoom && (!isMobile || !showRoomList)

  return (
    <div className={cn("flex h-full overflow-hidden bg-background", className)}>
      {/* Room list sidebar */}
      <div
        className={cn(
          "h-full transition-all",
          isMobile ? (showRoomList ? "w-full" : "hidden") : "w-80 shrink-0"
        )}
      >
        <RoomList
          rooms={rooms}
          currentRoom={currentRoom}
          currentUser={currentUser}
          onSelectRoom={handleSelectRoom}
          onSettings={onSettings}
          onJoinRoom={onJoinRoom}
          onCreateRoom={onCreateRoom}
        />
      </div>

      {/* Chat area */}
      {showChat ? (
        <div className="flex flex-1 flex-col">
          {/* Chat header */}
          <ChatHeader
            room={currentRoom}
            onBack={() => {
              if (isMobile) {
                setShowRoomList(true)
              }
              onBack?.()
            }}
            onSettings={onSettings}
            onLeaveRoom={onLeaveRoom}
          />

          <Separator />

          {/* Messages */}
          <ChatWindow
            messages={messages}
            currentUser={currentUser}
            isLoading={isLoadingMessages}
            typingUsers={typingUsers}
            onDeleteMessage={onDeleteMessage}
            className="flex-1"
          />

          {/* Input */}
          <ChatInput
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSendMessage}
          />
        </div>
      ) : (
        /* Empty state when no room selected */
        <div className="hidden flex-1 flex-col items-center justify-center p-8 md:flex">
          <div className="rounded-full bg-muted p-4">
            <Users className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="mt-4 text-lg font-medium">Welcome to Chat</h3>
          <p className="mt-2 text-center text-sm text-muted-foreground">
            Select a conversation from the sidebar to start chatting
          </p>
        </div>
      )}
    </div>
  )
}

interface ChatHeaderProps {
  room: Room
  onBack?: () => void
  onSettings?: () => void
  onLeaveRoom?: () => void
}

function ChatHeader({ room, onBack, onSettings, onLeaveRoom }: ChatHeaderProps) {
  const isMobile = useIsMobile()

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b px-4">
      <div className="flex items-center gap-3">
        {isMobile && (
          <Button variant="ghost" size="icon" onClick={onBack}>
            <ArrowLeft className="size-5" />
          </Button>
        )}

        {/* Room info */}
        {room.type === "direct" && room.participants && room.participants[0] ? (
          <div className="flex items-center gap-3">
            <UserAvatar
              user={room.participants[0]}
              size="md"
              showStatus={room.participants[0].is_online}
            />
            <div>
              <p className="font-medium">{room.name}</p>
              <p className="text-xs text-muted-foreground">
                {room.participants[0].is_online ? "Online" : "Offline"}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-full bg-primary/10">
              <Users className="size-4 text-primary" />
            </div>
            <div>
              <p className="font-medium">{room.name}</p>
              <p className="text-xs text-muted-foreground">
                {room.participants?.length || 0} members
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon">
            <MoreVertical className="size-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={onSettings}>
            Room settings
          </DropdownMenuItem>
          <DropdownMenuItem>Search in chat</DropdownMenuItem>
          <DropdownMenuItem>Mute notifications</DropdownMenuItem>
          {onLeaveRoom && (
            <DropdownMenuItem className="text-destructive" onClick={onLeaveRoom}>
              Leave room
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}

export default ChatLayout
