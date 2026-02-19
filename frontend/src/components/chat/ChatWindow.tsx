// ChatWindow component - displays the message list

import { useEffect, useRef, useState } from "react"
import { Loader2 } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import type { Message, User } from "@/lib/chat/types"
import MessageBubble from "./MessageBubble"

interface ChatWindowProps {
  messages: Message[]
  currentUser: User | null
  isLoading?: boolean
  isLoadingMore?: boolean
  hasMore?: boolean
  onLoadMore?: () => void
  onDeleteMessage?: (messageId: string) => void
  typingUsers?: Array<{ userId: string; username: string }>
  className?: string
}

export function ChatWindow({
  messages,
  currentUser,
  isLoading = false,
  isLoadingMore = false,
  hasMore = false,
  onLoadMore,
  onDeleteMessage,
  typingUsers = [],
  className,
}: ChatWindowProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (shouldAutoScroll && !isLoading) {
      scrollToBottom()
    }
  }, [messages, shouldAutoScroll, isLoading])

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const element = e.currentTarget
    const atTop = element.scrollTop < 100
    setShouldAutoScroll(atTop)

    // Load more when at top
    if (atTop && hasMore && !isLoadingMore && onLoadMore) {
      onLoadMore()
    }
  }

  // Group messages by date
  const groupedMessages = groupMessagesByDate(messages)

  if (isLoading) {
    return (
      <div className={cn("flex flex-1 items-center justify-center", className)}>
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className={cn("relative flex flex-1 flex-col", className)}>
      {/* Load more indicator */}
      {isLoadingMore && (
        <div className="flex items-center justify-center py-2">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Messages */}
      <ScrollArea
        ref={scrollRef}
        className="flex-1"
        onScroll={handleScroll}
      >
        <div className="flex min-h-full flex-col justify-end py-4">
          {messages.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="flex flex-col gap-1">
              {/* Date groups */}
              {Object.entries(groupedMessages).map(([date, dateMessages]) => (
                <div key={date}>
                  {/* Date separator */}
                  <div className="flex items-center justify-center py-4">
                    <span className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
                      {formatDateHeader(date)}
                    </span>
                  </div>

                  {/* Messages for this date */}
                  {dateMessages.map((message, index) => {
                    const showAvatar =
                      index === 0 ||
                      dateMessages[index - 1]?.user_id !== message.user_id
                    const isOwn = message.user_id === currentUser?.id

                    return (
                      <MessageBubble
                        key={message.id}
                        message={message}
                        isOwn={isOwn}
                        showAvatar={showAvatar}
                        onDelete={onDeleteMessage}
                      />
                    )
                  })}
                </div>
              ))}
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Typing indicator */}
      {typingUsers.length > 0 && (
        <div className="px-4 py-2">
          <TypingIndicator users={typingUsers} />
        </div>
      )}

      {/* Scroll to bottom button */}
      {!shouldAutoScroll && messages.length > 0 && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2">
          <button
            onClick={() => {
              scrollToBottom()
              setShouldAutoScroll(true)
            }}
            className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-lg transition hover:bg-primary/90"
          >
            New messages
          </button>
        </div>
      )}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
      <div className="rounded-full bg-muted p-4">
        <svg
          className="h-8 w-8 text-muted-foreground"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>
      </div>
      <p className="text-sm font-medium text-muted-foreground">No messages yet</p>
      <p className="text-xs text-muted-foreground">Start the conversation!</p>
    </div>
  )
}

function TypingIndicator({
  users,
}: {
  users: Array<{ userId: string; username: string }>
}) {
  if (users.length === 0) return null

  const names = users.map((u) => u.username).join(", ")

  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <div className="flex gap-1">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:300ms]" />
      </div>
      <span>
        {names}
        {users.length === 1 ? " is" : " are"} typing...
      </span>
    </div>
  )
}

function groupMessagesByDate(messages: Message[]): Record<string, Message[]> {
  const groups: Record<string, Message[]> = {}

  for (const message of messages) {
    const date = new Date(message.created_at).toDateString()

    if (!groups[date]) {
      groups[date] = []
    }

    groups[date].push(message)
  }

  return groups
}

function formatDateHeader(dateString: string): string {
  const date = new Date(dateString)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)

  if (date.toDateString() === today.toDateString()) {
    return "Today"
  }

  if (date.toDateString() === yesterday.toDateString()) {
    return "Yesterday"
  }

  return date.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  })
}

export default ChatWindow
