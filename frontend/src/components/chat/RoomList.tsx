// RoomList component - sidebar with chat rooms

import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { Users, MessageSquare, Plus, Search, Settings, LogOut } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import type { Room, User } from "@/lib/chat/types"
import UserAvatar from "./UserAvatar"

interface RoomListProps {
  rooms: Room[]
  currentRoom: Room | null
  currentUser: User | null
  onSelectRoom: (room: Room) => void
  onCreateRoom?: () => void
  onJoinRoom?: () => void
  onSettings?: () => void
  className?: string
}

export function RoomList({
  rooms,
  currentRoom,
  currentUser,
  onSelectRoom,
  onCreateRoom,
  onJoinRoom,
  onSettings,
  className,
}: RoomListProps) {
  const [searchQuery, setSearchQuery] = useState("")
  const navigate = useNavigate()

  const handleLogout = () => {
    localStorage.removeItem("access_token")
    localStorage.removeItem("sparkbot_room_id")
    navigate({ to: "/login" })
  }

  const filteredRooms = rooms.filter((room) =>
    room.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className={cn("flex h-full w-full flex-col border-r bg-muted/10", className)}>
      {/* Header */}
      <div className="flex items-center justify-between border-b p-4">
        <div className="flex items-center gap-2">
          <MessageSquare className="size-5" />
          <h2 className="font-semibold">Chats</h2>
        </div>
        <div className="flex items-center gap-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon">
                <Plus className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onCreateRoom}>
                <Users className="mr-2 size-4" />
                New Group
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onJoinRoom}>
                <MessageSquare className="mr-2 size-4" />
                Join Room
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {onSettings && (
            <Button variant="ghost" size="icon" onClick={onSettings}>
              <Settings className="size-4" />
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={handleLogout} title="Logout">
            <LogOut className="size-4" />
          </Button>
        </div>
      </div>

      {/* Search */}
      <div className="p-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Search chats..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Rooms list */}
      <ScrollArea className="flex-1">
        <div className="flex flex-col">
          {filteredRooms.length === 0 ? (
            <EmptyRoomsState onCreateRoom={onCreateRoom} onJoinRoom={onJoinRoom} />
          ) : (
            filteredRooms.map((room) => (
              <RoomItem
                key={room.id}
                room={room}
                isSelected={currentRoom?.id === room.id}
                onClick={() => onSelectRoom(room)}
              />
            ))
          )}
        </div>
      </ScrollArea>

      {/* Current user info */}
      {currentUser && (
        <div className="flex items-center gap-3 border-t p-4">
          <UserAvatar user={currentUser} size="md" showStatus />
          <div className="flex-1 overflow-hidden">
            <p className="truncate font-medium">
              {currentUser.display_name || currentUser.username}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              @{currentUser.username}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

interface RoomItemProps {
  room: Room
  isSelected?: boolean
  onClick?: () => void
}

function RoomItem({ room, isSelected, onClick }: RoomItemProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-3 border-b p-4 text-left transition-colors hover:bg-muted/50",
        isSelected && "bg-muted"
      )}
    >
      {/* Room avatar */}
      {room.type === "direct" && room.participants && room.participants[0] ? (
        <UserAvatar
          user={room.participants[0]}
          size="md"
          showStatus={room.participants[0].is_online}
        />
      ) : (
        <div className="flex size-9 items-center justify-center rounded-full bg-primary/10">
          <Users className="size-4 text-primary" />
        </div>
      )}

      {/* Room info */}
      <div className="flex-1 overflow-hidden">
        <div className="flex items-center justify-between">
          <p className="truncate font-medium">{room.name}</p>
          {room.unread_count && room.unread_count > 0 && (
            <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
              {room.unread_count > 99 ? "99+" : room.unread_count}
            </span>
          )}
        </div>

        {room.last_message && (
          <p className="mt-1 truncate text-sm text-muted-foreground">
            {room.last_message.content}
          </p>
        )}
      </div>
    </button>
  )
}

function EmptyRoomsState({
  onCreateRoom,
  onJoinRoom,
}: {
  onCreateRoom?: () => void
  onJoinRoom?: () => void
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-4 text-center">
      <div className="rounded-full bg-muted p-3">
        <Users className="h-6 w-6 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium text-muted-foreground">No chats yet</p>
      <p className="text-xs text-muted-foreground">
        Start a conversation or join a room
      </p>
      <div className="mt-2 flex gap-2">
        {onCreateRoom && (
          <Button variant="outline" size="sm" onClick={onCreateRoom}>
            <Plus className="mr-1 size-3" />
            New Group
          </Button>
        )}
        {onJoinRoom && (
          <Button variant="outline" size="sm" onClick={onJoinRoom}>
            <Users className="mr-1 size-3" />
            Join Room
          </Button>
        )}
      </div>
    </div>
  )
}

export default RoomList
