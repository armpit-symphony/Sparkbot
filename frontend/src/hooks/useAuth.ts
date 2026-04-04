import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import {
  type Body_login_login_access_token as AccessToken,
  LoginService,
  type UserPublic,
  type UserRegister,
  UsersService,
} from "@/client"
import {
  buildChatEntryHref,
  resolveChatEntryTarget,
} from "@/lib/sparkbotControls"
import { apiFetch } from "@/lib/apiBase"
import { handleError } from "@/utils"
import useCustomToast from "./useCustomToast"

const isLoggedIn = () => {
  return localStorage.getItem("access_token") !== null
}

const hasChatSession = () => {
  return (
    sessionStorage.getItem("chat_auth") !== null ||
    localStorage.getItem("access_token") !== null
  )
}

const useAuth = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const { data: user } = useQuery<UserPublic | null, Error>({
    queryKey: ["currentUser"],
    queryFn: UsersService.readUserMe,
    enabled: isLoggedIn(),
  })

  const signUpMutation = useMutation({
    mutationFn: (data: UserRegister) =>
      UsersService.registerUser({ requestBody: data }),
    onSuccess: () => {
      navigate({ to: "/login" })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const login = async (data: AccessToken) => {
    const response = await LoginService.loginAccessToken({
      formData: data,
    })
    localStorage.setItem("access_token", response.access_token)
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => {
      navigate({ to: "/" })
    },
    onError: handleError.bind(showErrorToast),
  })

  // Chat login using passphrase — sets HttpOnly cookie server-side
  const chatLogin = async (data: { passphrase: string }) => {
    const response = await apiFetch("/api/v1/chat/users/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || "Invalid passphrase")
    }

    // Store the bearer token so apiFetch can inject it as an Authorization header.
    // This is necessary in the desktop build where the cross-origin cookie
    // (tauri.localhost → 127.0.0.1) is blocked by the browser's SameSite policy.
    try {
      const data = await response.clone().json()
      if (data?.access_token) {
        sessionStorage.setItem("chat_token", data.access_token)
      }
    } catch { /* non-fatal */ }
    sessionStorage.setItem("chat_auth", "1")

    const target = await resolveChatEntryTarget()
    window.location.replace(buildChatEntryHref(target))
  }

  const chatLoginMutation = useMutation({
    mutationFn: chatLogin,
    onError: (error: Error) => {
      showErrorToast(error.message)
    },
  })

  const logout = () => {
    localStorage.removeItem("access_token")
    sessionStorage.removeItem("chat_auth")
    sessionStorage.removeItem("chat_token")
    // Clear server-side HttpOnly cookie
    apiFetch("/api/v1/chat/users/session", { method: "DELETE", credentials: "include" }).catch(() => {})
    navigate({ to: "/login" })
  }

  return {
    signUpMutation,
    loginMutation,
    chatLoginMutation,
    logout,
    user,
  }
}

export { hasChatSession, isLoggedIn }
export default useAuth
