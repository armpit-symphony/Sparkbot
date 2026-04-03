import { zodResolver } from "@hookform/resolvers/zod"
import {
  createFileRoute,
  redirect,
} from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { AuthLayout } from "@/components/Common/AuthLayout"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import { PasswordInput } from "@/components/ui/password-input"
import useAuth, { hasChatSession, isLoggedIn } from "@/hooks/useAuth"
import { apiFetch } from "@/lib/apiBase"
import { resolveChatEntryTarget } from "@/lib/sparkbotControls"

// Desktop (Tauri) builds ship with a bundled passphrase — no manual login needed.
function isDesktopApp(): boolean {
  if (typeof window === "undefined") return false
  const proto = window.location.protocol
  return proto === "tauri:" || proto === "asset:" || window.location.origin === "null"
}

const formSchema = z.object({
  passphrase: z
    .string()
    .min(1, { message: "Passphrase is required" }),
})

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/login")({
  component: Login,
  beforeLoad: async () => {
    // Desktop builds: auto-authenticate so users never see the login screen.
    if (isDesktopApp() && !isLoggedIn() && !hasChatSession()) {
      try {
        const res = await apiFetch("/api/v1/chat/users/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ passphrase: "sparkbot-local" }),
        })
        if (res.ok) {
          sessionStorage.setItem("chat_auth", "1")
        }
      } catch {
        // Auto-auth failed — fall through and show the login form
      }
    }
    if (isLoggedIn()) {
      throw redirect({
        to: "/",
      })
    }
    if (hasChatSession()) {
      const target = await resolveChatEntryTarget()
      throw redirect({
        to: target.to,
        search: target.search,
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: "Login - Sparkbot",
      },
    ],
  }),
})

function Login() {
  const { chatLoginMutation } = useAuth()
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onChange",
    criteriaMode: "all",
    defaultValues: {
      passphrase: "",
    },
  })

  const onSubmit = (data: FormData) => {
    if (chatLoginMutation.isPending) return
    chatLoginMutation.mutate(data)
  }

  return (
    <AuthLayout>
      <Form {...form}>
        <form
          noValidate
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-6"
        >
          <div className="flex flex-col items-center gap-2 text-center">
            <h1 className="text-2xl font-bold">Enter Sparkbot Passphrase</h1>
            <p className="text-sm text-muted-foreground">
              Enter your secret passphrase to access Sparkbot
            </p>
          </div>

          <div className="grid gap-4">
            <FormField
              control={form.control}
              name="passphrase"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Passphrase</FormLabel>
                  <FormControl>
                    <PasswordInput
                      placeholder="Enter your secret passphrase"
                      {...field}
                      formNoValidate
                    />
                  </FormControl>
                  <FormMessage className="text-xs" />
                </FormItem>
              )}
            />

            <LoadingButton type="submit" loading={chatLoginMutation.isPending}>
              Access Sparkbot
            </LoadingButton>
          </div>
        </form>
      </Form>
    </AuthLayout>
  )
}
