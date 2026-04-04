import { zodResolver } from "@hookform/resolvers/zod"
import {
  createFileRoute,
  redirect,
} from "@tanstack/react-router"
import { useEffect, useState } from "react"
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
import { ensureLocalChatSession, isLocalDesktopMode } from "@/lib/localSession"
import { resolveChatEntryTarget } from "@/lib/sparkbotControls"

const formSchema = z.object({
  passphrase: z
    .string()
    .min(1, { message: "Passphrase is required" }),
})

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/login")({
  component: Login,
  beforeLoad: async () => {
    if (!isLoggedIn() && !hasChatSession()) {
      await ensureLocalChatSession()
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
  const [isBootingLocal, setIsBootingLocal] = useState(isLocalDesktopMode() && !hasChatSession())
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onChange",
    criteriaMode: "all",
    defaultValues: {
      passphrase: "",
    },
  })

  useEffect(() => {
    if (!isLocalDesktopMode() || hasChatSession()) {
      setIsBootingLocal(false)
      return
    }

    let cancelled = false

    ensureLocalChatSession().finally(() => {
      if (!cancelled) {
        setIsBootingLocal(false)
        if (hasChatSession()) {
          window.location.replace("/dm")
        }
      }
    })

    return () => {
      cancelled = true
    }
  }, [])

  const onSubmit = (data: FormData) => {
    if (chatLoginMutation.isPending) return
    chatLoginMutation.mutate(data)
  }

  return (
    <AuthLayout>
      {isBootingLocal ? (
        <div className="flex flex-col gap-3 text-center">
          <h1 className="text-2xl font-bold">Starting Sparkbot</h1>
          <p className="text-sm text-muted-foreground">
            Your local Sparkbot install is waking up. This screen will disappear automatically.
          </p>
        </div>
      ) : (
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
      )}
    </AuthLayout>
  )
}
