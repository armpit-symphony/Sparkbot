// MessageBubble component - displays a single message

import { useState } from "react"
import { Check, Copy, Trash2, MoreHorizontal } from "lucide-react"
import ReactMarkdown from "react-markdown"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism"
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
  isStreaming?: boolean
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <button
      onClick={handleCopy}
      className="absolute right-2 top-2 rounded p-1 text-muted-foreground opacity-0 transition-opacity group-hover/code:opacity-100 hover:bg-muted hover:text-foreground"
      title="Copy code"
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </button>
  )
}

function CodeBlock({ children, className }: { children: string; className?: string }) {
  const match = /language-(\w+)/.exec(className || "")
  const isBlock = !!match || children.includes("\n")
  if (!isBlock) {
    return (
      <code className="rounded bg-muted/60 px-1 py-0.5 font-mono text-sm">
        {children}
      </code>
    )
  }
  return (
    <div className="group/code relative my-2">
      <CopyButton text={children} />
      <SyntaxHighlighter
        language={match?.[1] || "text"}
        style={oneDark}
        customStyle={{ borderRadius: "0.375rem", fontSize: "0.8rem", margin: 0 }}
        PreTag="div"
      >
        {children}
      </SyntaxHighlighter>
    </div>
  )
}

export function MessageBubble({
  message,
  isOwn = false,
  showAvatar = true,
  onDelete,
  isStreaming = false,
}: MessageBubbleProps) {
  const isBot = String(message.sender_type ?? "").toUpperCase() === "BOT"
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
          <UserAvatar user={message.user || {}} size="sm" showStatus={false} />
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
        {!isOwn && (message.sender_display_name || message.sender_username || message.user) && (
          <p className="mb-1 text-xs font-medium text-muted-foreground">
            {message.sender_display_name || message.sender_username || message.user?.display_name || message.user?.username}
          </p>
        )}

        {message.is_deleted ? (
          <p className="italic text-muted-foreground">This message has been deleted</p>
        ) : isBot ? (
          <div className="prose prose-sm dark:prose-invert max-w-none break-words">
            <ReactMarkdown
              components={{
                code({ className, children }) {
                  return <CodeBlock className={className}>{String(children).replace(/\n$/, "")}</CodeBlock>
                },
                p({ children }) {
                  return <p className="mb-2 last:mb-0">{children}</p>
                },
                ul({ children }) {
                  return <ul className="mb-2 ml-4 list-disc">{children}</ul>
                },
                ol({ children }) {
                  return <ol className="mb-2 ml-4 list-decimal">{children}</ol>
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
            {isStreaming && (
              <span className="inline-block h-4 w-2 animate-pulse bg-current opacity-70" />
            )}
          </div>
        ) : (
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
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
          {isStreaming && " · typing…"}
        </p>

        {/* Actions — only for non-streaming, non-deleted messages */}
        {!message.is_deleted && !isStreaming && (
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

  if (messageDate.getTime() === today.getTime()) return timeStr
  if (messageDate.getTime() === yesterday.getTime()) return `Yesterday ${timeStr}`
  return date.toLocaleDateString([], { month: "short", day: "numeric" }) + ", " + timeStr
}

export default MessageBubble
