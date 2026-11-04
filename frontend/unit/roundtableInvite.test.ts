import { describe, expect, test } from "bun:test"
import {
  appBasePath,
  buildAgentInvite,
  buildGuestLink,
  parseGuestFragment,
  suggestSlug,
} from "../src/lib/roundtableInvite"

const seat = {
  id: "s1",
  slug: "codex",
  display_name: "Codex",
  kind: "agent" as const,
  key: "rts_abc_def",
}
const ctx = {
  serverUrl: "https://sparkpitlabs.com/",
  roomId: "room-1",
  roomName: "Spark Pit Roundtable",
}

describe("roundtable invites", () => {
  test("base path keeps hosted mount prefix", () => {
    expect(appBasePath("/roundtable/meeting/room-1")).toBe("/roundtable")
    expect(appBasePath("/meeting/room-1")).toBe("")
  })

  test("guest link carries key only in the fragment and round-trips", () => {
    const link = buildGuestLink(
      "https://sparkpitlabs.com",
      "/roundtable",
      { ...seat, kind: "human" },
      ctx,
    )
    const url = new URL(link)
    expect(url.pathname).toBe("/roundtable/guest")
    expect(url.search).toBe("")
    expect(parseGuestFragment(url.hash)).toEqual({
      key: "rts_abc_def",
      roomId: "room-1",
    })
    expect(parseGuestFragment("#key=nope")).toBeNull()
  })

  test("agent invite has both setup paths and the right URLs", () => {
    const text = buildAgentInvite(seat, ctx)
    expect(text).toContain(
      "https://sparkpitlabs.com/api/v1/chat/seats/connector.py",
    )
    expect(text).toContain("--profile codex --url https://sparkpitlabs.com")
    expect(text).toContain("/api/v1/chat/seats/rooms/room-1/messages")
    expect(text).toContain('$env:SPARKBOT_SEAT_KEY="rts_abc_def"')
    expect(text).not.toContain("sparkpitlabs.com//")
  })

  test("slug suggestions match the server's rules", () => {
    expect(suggestSlug("Claude Code")).toBe("claude-code")
    expect(suggestSlug("A")).toBe("a-seat")
    expect(suggestSlug("!!")).toBe("guest-seat")
    for (const name of ["Codex", "Dana Smith", "x".repeat(80)]) {
      expect(suggestSlug(name)).toMatch(/^[a-z0-9][a-z0-9-]{1,30}$/)
    }
  })
})
