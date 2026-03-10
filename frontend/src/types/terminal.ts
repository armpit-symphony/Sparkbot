// ─── terminal.ts — shared terminal session types ──────────────────────────────

export type TerminalStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "disconnected"
  | "error"

export interface TerminalSessionInfo {
  sessionId: string
  userId: string
  host: string
  shell: string
  status: TerminalStatus
  startedAt: number
  lastActivityAt: number
  stationId?: string | null
}

// WebSocket message shapes

export interface WsConnectedMsg {
  type: "connected"
  session_id: string
  host: string
  shell: string
  started_at: number
}

export interface WsOutputMsg {
  type: "output"
  /** base64-encoded PTY bytes */
  data: string
}

export interface WsStatusMsg {
  type: "status"
  session_id: string
  status: string
}

export interface WsErrorMsg {
  type: "error"
  message: string
}

export interface WsClosedMsg {
  type: "closed"
  reason: string
}

export type WsServerMsg =
  | WsConnectedMsg
  | WsOutputMsg
  | WsStatusMsg
  | WsErrorMsg
  | WsClosedMsg

// Client → server
export interface WsInputMsg {
  type: "input"
  /** base64-encoded keystroke bytes */
  data: string
}

export interface WsResizeMsg {
  type: "resize"
  cols: number
  rows: number
}

export interface WsCloseMsg {
  type: "close"
}

export type WsClientMsg = WsInputMsg | WsResizeMsg | WsCloseMsg
