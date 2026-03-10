// ─── useTerminalSession.ts ────────────────────────────────────────────────────
// Manages the lifecycle of a single terminal session:
//   create (HTTP) → WebSocket connect → stream → disconnect/close.
//
// Usage:
//   const { sessionInfo, ws, connect, disconnect, error } = useTerminalSession(stationId)

import { useCallback, useRef, useState } from "react"
import type { TerminalSessionInfo, TerminalStatus } from "@/types/terminal"

const API_BASE = "/api/v1/terminal"

function buildWsUrl(sessionId: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${proto}//${window.location.host}${API_BASE}/ws/${sessionId}`
}

export interface UseTerminalSessionReturn {
  sessionInfo: TerminalSessionInfo | null
  ws: WebSocket | null
  error: string | null
  connect: (stationId?: string) => Promise<void>
  disconnect: () => void
}

export function useTerminalSession(
  stationId: string,
): UseTerminalSessionReturn {
  const [sessionInfo, setSessionInfo] = useState<TerminalSessionInfo | null>(null)
  const [ws, setWs] = useState<WebSocket | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Keep a ref so disconnect() can close the current ws without stale closure
  const wsRef = useRef<WebSocket | null>(null)
  const sessionRef = useRef<TerminalSessionInfo | null>(null)

  const setStatus = useCallback((status: TerminalStatus) => {
    setSessionInfo((prev) => (prev ? { ...prev, status } : null))
  }, [])

  const connect = useCallback(async () => {
    // Clean up any existing connection
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
      setWs(null)
    }

    setError(null)
    setSessionInfo({ sessionId: "", userId: "", host: "localhost", shell: "/bin/bash", status: "connecting", startedAt: 0, lastActivityAt: 0, stationId })

    // ── Create session via HTTP ───────────────────────────────────────────────
    let session: TerminalSessionInfo
    try {
      const res = await fetch(`${API_BASE}/sessions`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          host: "localhost",
          shell: "/bin/bash",
          station_id: stationId,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(body.detail ?? `HTTP ${res.status}`)
      }
      const raw = await res.json()
      session = {
        sessionId: raw.session_id,
        userId: raw.user_id,
        host: raw.host,
        shell: raw.shell,
        status: "connecting",
        startedAt: raw.started_at,
        lastActivityAt: raw.last_activity_at,
        stationId: raw.station_id ?? stationId,
      }
      sessionRef.current = session
      setSessionInfo(session)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      setSessionInfo(null)
      return
    }

    // ── Open WebSocket ────────────────────────────────────────────────────────
    const websocket = new WebSocket(buildWsUrl(session.sessionId))
    wsRef.current = websocket

    websocket.onopen = () => {
      // Cookie auth is automatic (same origin). Nothing extra needed.
    }

    websocket.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data as string)
        if (msg.type === "connected") {
          setSessionInfo((prev) =>
            prev ? { ...prev, status: "connected", sessionId: msg.session_id } : null,
          )
        } else if (msg.type === "status") {
          setStatus(msg.status as TerminalStatus)
        } else if (msg.type === "closed") {
          setStatus("disconnected")
          wsRef.current = null
          setWs(null)
        } else if (msg.type === "error") {
          setError(msg.message)
        }
      } catch {
        // ignore parse errors
      }
    }

    websocket.onclose = () => {
      wsRef.current = null
      setWs(null)
      setSessionInfo((prev) =>
        prev && prev.status !== "disconnected"
          ? { ...prev, status: "disconnected" }
          : prev,
      )
    }

    websocket.onerror = () => {
      setError("WebSocket connection failed")
      setStatus("error")
    }

    setWs(websocket)
  }, [stationId, setStatus])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      try {
        wsRef.current.send(JSON.stringify({ type: "close" }))
      } catch {
        /* already closed */
      }
      wsRef.current.close()
      wsRef.current = null
    }

    // Best-effort HTTP close
    if (sessionRef.current?.sessionId) {
      fetch(`${API_BASE}/sessions/${sessionRef.current.sessionId}`, {
        method: "DELETE",
        credentials: "include",
      }).catch(() => {})
    }

    setWs(null)
    setSessionInfo(null)
    setError(null)
    sessionRef.current = null
  }, [])

  return { sessionInfo, ws, error, connect, disconnect }
}
