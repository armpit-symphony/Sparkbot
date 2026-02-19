// UserAvatar component - displays user avatar with online status

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"
import type { User } from "@/lib/chat/types"

interface UserAvatarProps {
  user: Partial<User>
  size?: "sm" | "md" | "lg" | "xl"
  showStatus?: boolean
  className?: string
}

const sizeClasses = {
  sm: "size-6 text-xs",
  md: "size-8 text-sm",
  lg: "size-10 text-base",
  xl: "size-14 text-lg",
}

const statusSizeClasses = {
  sm: "size-1.5",
  md: "size-2",
  lg: "size-2.5",
  xl: "size-3",
}

export function UserAvatar({ user, size = "md", showStatus = false, className }: UserAvatarProps) {
  const initials = getInitials(user.display_name || user.username || "?")
  const statusColor = user.is_online ? "bg-green-500" : "bg-gray-400"

  return (
    <div className={cn("relative inline-block", className)}>
      <Avatar className={cn(sizeClasses[size])}>
        {user.avatar_url && <AvatarImage src={user.avatar_url} alt={user.display_name || user.username} />}
        <AvatarFallback className="bg-muted">{initials}</AvatarFallback>
      </Avatar>
      {showStatus && (
        <span
          className={cn(
            "absolute bottom-0 right-0 rounded-full border-2 border-background",
            statusSizeClasses[size],
            statusColor
          )}
        />
      )}
    </div>
  )
}

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2)
}

export default UserAvatar
