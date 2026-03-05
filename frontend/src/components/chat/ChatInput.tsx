// ChatInput component - message composer

import { useState, useRef } from "react"
import { Send } from "lucide-react"
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
  className,
}: ChatInputProps) {
  const [isFocused, setIsFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (value.trim()) {
        onSubmit(value)
      }
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value)
    onTyping?.()
  }

  return (
    <div
      className={cn(
        "flex items-center gap-2 border-t bg-background px-4 py-3",
        isFocused && "ring-2 ring-ring/20",
        className
      )}
    >
      <Input
        ref={inputRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        placeholder={placeholder}
        disabled={disabled || isLoading}
        className="flex-1"
      />
      <Button
        variant={value.trim() ? "default" : "ghost"}
        size="icon"
        onClick={() => onSubmit(value)}
        disabled={disabled || isLoading || !value.trim()}
        className={cn(value.trim() && "bg-primary text-primary-foreground")}
      >
        <Send className="size-5" />
      </Button>
    </div>
  )
}

export default ChatInput
