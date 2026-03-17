// ─── useTerminalSession.ts ────────────────────────────────────────────────────
// Manages the lifecycle of a single terminal session:
//   reconnect (if stored) or create (HTTP) → WebSocket connect → stream → disconnect/close.
//
// Session persistence: session_id is stored in sessionStorage keyed by station_id so that
// navigating away and back reconnects to the existing PTY instead of creating a new one.
//
// Usage:
//   const { sessionInfo, ws, connect, disconnect, listSessions, error } = useTerminalSession(stationId, { host, shell })
//   host defaults to "localhost". Set to a whitelisted remote host for SSH sessions.

import { useCallback, useEffect, useRef, useState } from "react"
import type { TerminalSessionInfo, TerminalStatus } from "@/types/terminal"

const API_BASE = "/api/v1/terminal"

function buildWsUrl(sessionId: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${proto}//${window.location.host}${API_BASE}/ws/${sessionId}`
}

function storageKey(stationId: string): string {
  return `terminal:session:${stationId}`
}

function saveSessionId(stationId: string, sessionId: string): void {
  try { sessionStorage.setItem(storageKey(stationId), sessionId) } catch { /* ignore */ }
}

function loadSessionId(stationId: string): string | null {
  try { return sessionStorage.getItem(storageKey(stationId)) } catch { return null }
}

function clearSessionId(stationId: string): void {
  try { sessionStorage.removeItem(storageKey(stationId)) } catch { /* ignore */ }
}

async function fetchSessionList(): Promise<TerminalSessionInfo[]> {
  const res = await fetch(`${API_BASE}/sessions`, { credentials: "include" })
  if (!res.ok) return []
  const data: Array<{
    session_id: string; user_id: string; host: string; shell: string
    status: string; started_at: number; last_activity_at: number; station_id?: string
  }> = await res.json()
  return data.map((r) => ({
    sessionId: r.session_id,
    userId: r.user_id,
    host: r.host,
    shell: r.shell,
    status: r.status as TerminalStatus,
    startedAt: r.started_at,
    lastActivityAt: r.last_activity_at,
    stationId: r.station_id ?? "",
  }))
}

export interface UseTerminalSessionReturn {
  sessionInfo: TerminalSessionInfo | null
  ws: WebSocket | null
  error: string | null
  connect: (stationId?: string) => Promise<void>
  disconnect: () => void
  listSessions: () => Promise<TerminalSessionInfo[]>
}

export interface UseTerminalSessionOpts {
  host?: string   // defaults to "localhost"; set to a whitelisted remote host for SSH
  shell?: string  // defaults to "/bin/bash"; ignored for SSH sessions
}

export function useTerminalSession(
  stationId: string,
  opts: UseTerminalSessionOpts = {},
): UseTerminalSessionReturn {
  const [sessionInfo, setSessionInfo] = useState<TerminalSessionInfo | null>(null)
  const [ws, setWs] = useState<WebSocket | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Keep refs so callbacks can access current values without stale closures
  const wsRef = useRef<WebSocket | null>(null)
  const sessionRef = useRef<TerminalSessionInfo | null>(null)

  const setStatus = useCallback((status: TerminalStatus) => {
    setSessionInfo((prev) => (prev ? { ...prev, status } : null))
  }, [])

  // ── Open WebSocket to an already-known session ────────────────────────────
  const _openWs = useCallback((session: TerminalSessionInfo) => {
    const websocket = new WebSocket(buildWsUrl(session.sessionId))
    wsRef.current = websocket

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
          clearSessionId(stationId)
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

  // ── Main connect: try stored session first, fall back to creating new ─────
  const connect = useCallback(async () => {
    // Clean up any existing connection
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
      setWs(null)
    }

    setError(null)
    setSessionInfo({ sessionId: "", userId: "", host: "localhost", shell: "/bin/bash", status: "connecting", startedAt: 0, lastActivityAt: 0, stationId })

    // Try to reconnect to a stored session for this station
    const storedId = loadSessionId(stationId)
    if (storedId) {
      try {
        const sessions = await fetchSessionList()
        const existing = sessions.find((s) => s.sessionId === storedId)
        if (existing) {
          sessionRef.current = existing
          setSessionInfo({ ...existing, status: "connecting" })
          _openWs(existing)
          return
        }
      } catch {
        // fall through to create new
      }
      clearSessionId(stationId)
    }

    // ── Create new session via HTTP ──────────────────────────────────────────
    let session: TerminalSessionInfo
    try {
      const res = await fetch(`${API_BASE}/sessions`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          host: opts.host || "localhost",
          shell: opts.shell || "/bin/bash",
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
      saveSessionId(stationId, session.sessionId)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      setSessionInfo(null)
      return
    }

    _openWs(session)
  }, [stationId, _openWs])

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

    clearSessionId(stationId)
    setWs(null)
    setSessionInfo(null)
    setError(null)
    sessionRef.current = null
  }, [stationId])

  const listSessions = useCallback((): Promise<TerminalSessionInfo[]> => fetchSessionList(), [])

  // Cleanup WS on unmount (don't close the server session — it persists for reconnect)
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [])

  return { sessionInfo, ws, error, connect, disconnect, listSessions }
}
