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

  // Chat login using passphrase
  const chatLogin = async (data: { passphrase: string }) => {
    const response = await fetch("/api/v1/chat/users/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || "Invalid passphrase")
    }

    const result = await response.json()
    localStorage.setItem("access_token", result.access_token)
    
    // Hard redirect to /dm - no React routing
    window.location.replace("/dm")
    console.log("[AUTH] Bootstrap fetch for rooms...")
    fetch("/api/v1/chat/rooms", {
      headers: {
        Authorization: `Bearer ${result.access_token}`,
      },
    })
      .then(async (res) => {
        console.log("[AUTH] Bootstrap rooms status:", res.status)
        const text = await res.text()
        console.log("[AUTH] Bootstrap rooms body:", text.slice(0, 200))
      })
      .catch((e) => {
        console.error("[AUTH] Bootstrap rooms error:", e)
      })
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
