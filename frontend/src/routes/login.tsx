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
import useAuth, { isLoggedIn } from "@/hooks/useAuth"

const formSchema = z.object({
  passphrase: z
    .string()
    .min(1, { message: "Passphrase is required" }),
})

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/login")({
  component: Login,
  beforeLoad: async () => {
    if (isLoggedIn()) {
      throw redirect({
        to: "/chat",
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
