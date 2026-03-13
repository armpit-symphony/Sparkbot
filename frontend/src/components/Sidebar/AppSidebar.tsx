import { Bot, Home, LayoutGrid, MessageSquare, Settings, Users } from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { isV1LocalMode } from "@/lib/v1Local"
import { type Item, Main } from "./Main"
import { User } from "./User"

const baseItems: Item[] = [
  { icon: LayoutGrid, title: "Workstation", path: "/workstation" },
  { icon: Home, title: "Dashboard", path: "/" },
  { icon: Bot, title: "Sparkbot", path: "/dm" },
  { icon: MessageSquare, title: "Chat", path: "/chat" },
  { icon: Settings, title: "Settings", path: "/settings" },
]

export function AppSidebar() {
  const { user: currentUser } = useAuth()
  const visibleBaseItems = isV1LocalMode
    ? baseItems.filter((item) => item.path !== "/workstation")
    : baseItems

  const items = currentUser?.is_superuser
    ? [...visibleBaseItems, { icon: Users, title: "Admin", path: "/admin" }]
    : visibleBaseItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
