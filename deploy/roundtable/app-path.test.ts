import { expect, test } from "bun:test"
import { appPath } from "../../frontend/src/lib/appPath"

test("root installs keep their original login and meeting URLs", () => {
  expect(appPath("/login", "/")).toBe("/login")
  expect(appPath("/meeting/room-id?tab=notes", "/")).toBe("/meeting/room-id?tab=notes")
})

test("hosted paths preserve route, query, and fragment", () => {
  expect(appPath("/login", "/roundtable/")).toBe("/roundtable/login")
  expect(appPath("/meeting/room-id?tab=notes#decisions", "/roundtable/")).toBe(
    "/roundtable/meeting/room-id?tab=notes#decisions",
  )
  expect(appPath("/", "/roundtable/")).toBe("/roundtable/")
})
