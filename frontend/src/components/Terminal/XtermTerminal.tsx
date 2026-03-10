// ─── XtermTerminal.tsx ────────────────────────────────────────────────────────
// Self-contained xterm.js terminal component.
//
// Props:
//   ws         — live WebSocket (null = not connected, terminal shows idle)
//   accentHex  — color used for cursor / selection to match station theme
//
// Wiring:
//   - xterm onData  → WS send  {type:"input", data: base64}
//   - xterm onResize → WS send {type:"resize", cols, rows}
//   - WS "output"   → terminal.write(decoded bytes)
//   - ResizeObserver → FitAddon.fit() → triggers xterm onResize
//
// The component is pure display + event bridge. Session lifecycle is owned
// by the parent via useTerminalSession.

import { useEffect, useRef } from "react"
import { Terminal } from "@xterm/xterm"
import { FitAddon } from "@xterm/addon-fit"
import "@xterm/xterm/css/xterm.css"

interface XtermTerminalProps {
  ws: WebSocket | null
  accentHex?: string
  onConnected?: () => void
  onDisconnected?: () => void
}

// base64 decode to Uint8Array (browser native)
function b64ToUint8(b64: string): Uint8Array {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

// Encode string to base64 via TextEncoder (handles all Unicode / escape codes)
function strToB64(str: string): string {
  const bytes = new TextEncoder().encode(str)
  let binary = ""
  bytes.forEach((b) => (binary += String.fromCharCode(b)))
  return btoa(binary)
}

export function XtermTerminal({
  ws,
  accentHex = "#4ade80",
  onConnected,
  onDisconnected,
}: XtermTerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)

  // ── Initialize xterm once on mount ───────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "block",
      fontSize: 13,
      fontFamily: '"Cascadia Code", "Fira Code", "Courier New", monospace',
      theme: {
        background: "#030508",
        foreground: "#d1d5db",
        cursor: accentHex,
        selectionBackground: `${accentHex}55`,
        black: "#111827",
        red: "#f87171",
        green: "#4ade80",
        yellow: "#fbbf24",
        blue: "#60a5fa",
        magenta: "#a78bfa",
        cyan: "#22d3ee",
        white: "#e5e7eb",
        brightBlack: "#374151",
        brightRed: "#fca5a5",
        brightGreen: "#86efac",
        brightYellow: "#fde68a",
        brightBlue: "#93c5fd",
        brightMagenta: "#c4b5fd",
        brightCyan: "#67e8f9",
        brightWhite: "#f9fafb",
      },
      allowTransparency: true,
      scrollback: 2000,
      convertEol: false,
    })

    const fitAddon = new FitAddon()
    term.loadAddon(fitAddon)
    term.open(containerRef.current)

    // Initial fit (deferred one frame so the container has rendered dimensions)
    requestAnimationFrame(() => {
      try {
        fitAddon.fit()
      } catch {
        /* element not ready yet */
      }
    })

    termRef.current = term
    fitAddonRef.current = fitAddon

    // Resize observer — keep terminal cols/rows matched to container
    const ro = new ResizeObserver(() => {
      try {
        fitAddon.fit()
      } catch {
        /* element unmounted */
      }
    })
    if (containerRef.current) ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      term.dispose()
      termRef.current = null
      fitAddonRef.current = null
    }
    // intentionally runs once — accentHex changes would require re-init
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Wire WebSocket ────────────────────────────────────────────────────────
  useEffect(() => {
    const term = termRef.current
    if (!term) return

    if (!ws) {
      // Disconnected — show idle cursor
      return
    }

    // Input: user typing → WS
    const dataDispose = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data: strToB64(data) }))
      }
    })

    // Resize: terminal size change → WS
    const resizeDispose = term.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols, rows }))
      }
    })

    // Output: WS → terminal
    const handleMessage = (evt: MessageEvent) => {
      try {
        const msg = JSON.parse(evt.data as string)
        if (msg.type === "output") {
          term.write(b64ToUint8(msg.data as string))
        } else if (msg.type === "connected") {
          onConnected?.()
          // Initial resize after connecting
          requestAnimationFrame(() => {
            try {
              fitAddonRef.current?.fit()
            } catch {
              /* ok */
            }
          })
        } else if (msg.type === "closed") {
          onDisconnected?.()
          term.writeln("\r\n\x1b[33m[session closed]\x1b[0m")
        } else if (msg.type === "error") {
          term.writeln(`\r\n\x1b[31m[error: ${msg.message}]\x1b[0m`)
        }
      } catch {
        /* ignore parse errors */
      }
    }

    ws.addEventListener("message", handleMessage)

    // Initial resize to inform the backend of current dimensions
    requestAnimationFrame(() => {
      try {
        fitAddonRef.current?.fit()
      } catch {
        /* ok */
      }
    })

    return () => {
      dataDispose.dispose()
      resizeDispose.dispose()
      ws.removeEventListener("message", handleMessage)
    }
  }, [ws, onConnected, onDisconnected])

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        // xterm.css renders into this container; background matches theme
        backgroundColor: "#030508",
      }}
    />
  )
}
