export const ROUND_TABLE_SEAT_COUNT = 6

const WORKSTATION_MEETING_DRAFT_KEY = "sparkbot_workstation_roundtable_draft"
const WORKSTATION_MEETING_META_PREFIX = "sparkbot_workstation_meeting_room:"

export interface WorkstationMeetingDraft {
  seats: Array<string | null>
  roomId: string | null
  roomName: string
}

export interface WorkstationMeetingSeatMeta {
  seatIndex: number
  stationId: string
  label: string
  accentHex: string
}

export interface WorkstationMeetingRoomMeta {
  roomId: string
  roomName: string
  launchedAt: string
  protocolLabel: string
  seats: WorkstationMeetingSeatMeta[]
}

export function buildEmptyMeetingDraft(): WorkstationMeetingDraft {
  return {
    seats: new Array(ROUND_TABLE_SEAT_COUNT).fill(null),
    roomId: null,
    roomName: "Roundtable",
  }
}

export function normalizeMeetingSeats(
  seats: Array<string | null> | undefined,
): Array<string | null> {
  return new Array(ROUND_TABLE_SEAT_COUNT)
    .fill(null)
    .map((_, index) => seats?.[index] ?? null)
}

export function loadMeetingDraft(): WorkstationMeetingDraft {
  if (typeof window === "undefined") return buildEmptyMeetingDraft()

  try {
    const raw = window.localStorage.getItem(WORKSTATION_MEETING_DRAFT_KEY)
    if (!raw) return buildEmptyMeetingDraft()
    const parsed = JSON.parse(raw) as Partial<WorkstationMeetingDraft>
    return {
      seats: normalizeMeetingSeats(parsed.seats),
      roomId: parsed.roomId ?? null,
      roomName: parsed.roomName || "Roundtable",
    }
  } catch {
    return buildEmptyMeetingDraft()
  }
}

export function saveMeetingDraft(draft: WorkstationMeetingDraft): void {
  if (typeof window === "undefined") return
  window.localStorage.setItem(
    WORKSTATION_MEETING_DRAFT_KEY,
    JSON.stringify({
      seats: normalizeMeetingSeats(draft.seats),
      roomId: draft.roomId ?? null,
      roomName: draft.roomName || "Roundtable",
    }),
  )
}

export function saveMeetingRoomMeta(meta: WorkstationMeetingRoomMeta): void {
  if (typeof window === "undefined") return
  window.localStorage.setItem(
    `${WORKSTATION_MEETING_META_PREFIX}${meta.roomId}`,
    JSON.stringify(meta),
  )
}

export function loadMeetingRoomMeta(roomId: string): WorkstationMeetingRoomMeta | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(`${WORKSTATION_MEETING_META_PREFIX}${roomId}`)
    if (!raw) return null
    return JSON.parse(raw) as WorkstationMeetingRoomMeta
  } catch {
    return null
  }
}
