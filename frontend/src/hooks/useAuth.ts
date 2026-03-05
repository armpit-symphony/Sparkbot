import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import {
  type Body_login_login_access_token as AccessToken,
  LoginService,
  type UserPublic,
  type UserRegister,
  UsersService,
} from "@/client"
import { handleError } from "@/utils"
import useCustomToast from "./useCustomToast"

const isLoggedIn = () => {
  return localStorage.getItem("access_token") !== null
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
    const response = await fetch("/api/v1/chat/users/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || "Invalid passphrase")
    }

    // Server sets HttpOnly cookie — we only store a presence flag
    sessionStorage.setItem("chat_auth", "1")

    // Hard redirect to /dm
    window.location.replace("/dm")
  }

  const chatLoginMutation = useMutation({
    mutationFn: chatLogin,
    onSuccess: () => {
      navigate({ to: "/chat" })
    },
    onError: (error: Error) => {
      showErrorToast(error.message)
    },
  })

  const logout = () => {
    localStorage.removeItem("access_token")
    sessionStorage.removeItem("chat_auth")
    // Clear server-side HttpOnly cookie
    fetch("/api/v1/chat/users/session", { method: "DELETE", credentials: "include" }).catch(() => {})
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

export { isLoggedIn }
export default useAuth
