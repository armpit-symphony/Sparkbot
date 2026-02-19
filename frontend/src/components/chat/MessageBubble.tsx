// MessageBubble component - displays a single message

import { MoreHorizontal, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import type { Message } from "@/lib/chat/types"
import UserAvatar from "./UserAvatar"

interface MessageBubbleProps {
  message: Message
  isOwn?: boolean
  showAvatar?: boolean
  onDelete?: (messageId: string) => void
}

export function MessageBubble({ message, isOwn = false, showAvatar = true, onDelete }: MessageBubbleProps) {
  const formattedTime = formatMessageTime(message.created_at)

  return (
    <div
      className={cn(
        "group flex gap-2 px-4 py-1",
        isOwn ? "flex-row-reverse" : "flex-row"
      )}
    >
      {showAvatar && (
        <div className={cn("mt-auto", isOwn ? "order-2" : "order-1")}>
          <UserAvatar
            user={message.user || {}}
            size="sm"
            showStatus={false}
          />
        </div>
      )}

      <div
        className={cn(
          "relative max-w-[70%] rounded-2xl px-4 py-2",
          isOwn
            ? "order-1 rounded-br-md bg-primary text-primary-foreground"
            : "order-2 rounded-bl-md bg-muted"
        )}
      >
        {!isOwn && message.user && (
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            {message.user.display_name || message.user.username}
          </p>
        )}

        {message.is_deleted ? (
          <p className="italic text-muted-foreground">This message has been deleted</p>
        ) : (
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        )}

        {/* Reactions */}
        {message.reactions && message.reactions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.reactions.map((reaction, index) => (
              <span
                key={index}
                className="inline-flex items-center rounded-full bg-muted/50 px-1.5 py-0.5 text-xs"
              >
                {reaction.emoji}
              </span>
            ))}
          </div>
        )}

        {/* Time */}
        <p
          className={cn(
            "mt-1 text-[10px] opacity-70",
            isOwn ? "text-primary-foreground/70" : "text-muted-foreground"
          )}
        >
          {formattedTime}
          {message.is_edited && " (edited)"}
        </p>

        {/* Actions */}
        {!message.is_deleted && (
          <div
            className={cn(
              "absolute top-0 opacity-0 transition-opacity group-hover:opacity-100",
              isOwn ? "-left-8" : "-right-8"
            )}
          >
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" className="size-6">
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align={isOwn ? "end" : "start"}>
                <DropdownMenuItem>Add reaction</DropdownMenuItem>
                <DropdownMenuItem>Reply</DropdownMenuItem>
                {isOwn && (
                  <DropdownMenuItem
                    className="text-destructive"
                    onClick={() => onDelete?.(message.id)}
                  >
                    <Trash2 className="mr-2 size-4" />
                    Delete
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </div>
    </div>
  )
}

function formatMessageTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const messageDate = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  
  const timeStr = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  
  if (messageDate.getTime() === today.getTime()) {
    return timeStr
  }
  
  if (messageDate.getTime() === yesterday.getTime()) {
    return `Yesterday ${timeStr}`
  }
  
  return date.toLocaleDateString([], { month: "short", day: "numeric" }) + ", " + timeStr
}

export default MessageBubble
