// ChatInput component - message composer

import { useState, useRef, useCallback } from "react"
import { Image, Paperclip, Send, Smile, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSubmit: (content: string) => void
  onTyping?: () => void
  placeholder?: string
  disabled?: boolean
  isLoading?: boolean
  attachments?: File[]
  onAddAttachment?: (file: File) => void
  onRemoveAttachment?: (index: number) => void
  className?: string
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  onTyping,
  placeholder = "Type a message...",
  disabled = false,
  isLoading = false,
  attachments = [],
  onAddAttachment,
  onRemoveAttachment,
  className,
}: ChatInputProps) {
  const [isFocused, setIsFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (value.trim() || attachments.length > 0) {
        onSubmit(value)
      }
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value)
    onTyping?.()
  }

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file && onAddAttachment) {
        onAddAttachment(file)
      }
      e.target.value = ""
    },
    [onAddAttachment]
  )

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const files = Array.from(e.clipboardData.files).filter((file) =>
        file.type.startsWith("image/")
      )
      if (files.length > 0 && onAddAttachment) {
        files.forEach((file) => onAddAttachment(file))
      }
    },
    [onAddAttachment]
  )

  const showSendButton = value.trim() || attachments.length > 0

  return (
    <div
      className={cn(
        "flex flex-col gap-2 border-t bg-background px-4 py-3",
        isFocused && "ring-2 ring-ring/20",
        className
      )}
    >
      {/* Attachments preview */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {attachments.map((file, index) => (
            <div
              key={index}
              className="relative flex items-center gap-2 rounded-md border bg-muted/50 px-2 py-1 text-sm"
            >
              <span className="max-w-[150px] truncate">{file.name}</span>
              <Button
                variant="ghost"
                size="icon-sm"
                className="size-5"
                onClick={() => onRemoveAttachment?.(index)}
              >
                <X className="size-3" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-center gap-2">
        {/* Attachment buttons */}
        <div className="flex items-center gap-1">
          <input
            type="file"
            id="chat-file-input"
            className="hidden"
            accept="*/*"
            onChange={handleFileSelect}
          />
          <Button
            variant="ghost"
            size="icon"
            className="text-muted-foreground"
            onClick={() => document.getElementById("chat-file-input")?.click()}
            disabled={disabled}
          >
            <Paperclip className="size-5" />
          </Button>

          <input
            type="file"
            id="chat-image-input"
            className="hidden"
            accept="image/*"
            onChange={handleFileSelect}
          />
          <Button
            variant="ghost"
            size="icon"
            className="text-muted-foreground"
            onClick={() => document.getElementById("chat-image-input")?.click()}
            disabled={disabled}
          >
            <Image className="size-5" />
          </Button>

          <Button variant="ghost" size="icon" className="text-muted-foreground" disabled={disabled}>
            <Smile className="size-5" />
          </Button>
        </div>

        {/* Message input */}
        <Input
          ref={inputRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onPaste={handlePaste}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          className="flex-1"
        />

        {/* Send button */}
        <Button
          variant={showSendButton ? "default" : "ghost"}
          size="icon"
          onClick={() => onSubmit(value)}
          disabled={disabled || isLoading || (!value.trim() && attachments.length === 0)}
          className={cn(showSendButton && "bg-primary text-primary-foreground")}
        >
          <Send className="size-5" />
        </Button>
      </div>
    </div>
  )
}

export default ChatInput
