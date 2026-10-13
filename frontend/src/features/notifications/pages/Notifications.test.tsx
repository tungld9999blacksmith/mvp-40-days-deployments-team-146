import { beforeEach, describe, expect, it, vi } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import { ApiError } from "@/shared/api/client"
import type { QueryState } from "@/shared/hooks/useCachedQuery"
import { useCachedQuery } from "@/shared/hooks/useCachedQuery"
import { useNotificationSettings } from "../hooks/useNotificationSettings"
import type { FeedEntry } from "../feed"
import type { NotificationSettings } from "../types"
import Notifications from "./Notifications"

vi.mock("@/shared/hooks/useCachedQuery", () => ({ useCachedQuery: vi.fn() }))
vi.mock("../hooks/useNotificationSettings", () => ({
  useNotificationSettings: vi.fn(),
}))

const settingsData: NotificationSettings = {
  remindersEnabled: false,
  reminderLeadDays: 14,
  defaultReminderLeadDays: 7,
  channels: [],
}
const retry = vi.fn()
const state = <T,>(data: T | null, error: QueryState<T>["error"] = null) => ({
  data,
  error,
  isFetching: false,
  fetchedAt: null,
  isLoading: data === null && !error,
  refetch: retry,
})
const render = (variant: "owner" | "portal" = "owner") =>
  renderToStaticMarkup(
    <MemoryRouter>
      <Notifications variant={variant} />
    </MemoryRouter>,
  )

function task(id: string): FeedEntry {
  return {
    id,
    tone: "warning",
    title: `Thông báo ${id}`,
    message: "Lời nhắc chưa giải quyết",
    at: "",
    unread: false,
    action: { label: "Xem lời nhắc", to: `/notifications/reminders/${id}` },
    attention: {
      category: "maintenance",
      label: "Bảo dưỡng",
      title: `Mốc ${id}`,
      description: "Gần tới hạn bảo dưỡng",
      priority: 1,
    },
  }
}

describe("notifications rail", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useCachedQuery).mockReturnValue(state([]))
    vi.mocked(useNotificationSettings).mockReturnValue(state(settingsData))
  })

  it("counts all pending work, shows three actions and uses actual saved reminder settings", () => {
    vi.mocked(useCachedQuery).mockReturnValue(
      state([task("1"), task("2"), task("3"), task("4")]),
    )
    const html = render()
    expect(html).toContain("4 việc cần bạn xem")
    expect(html).toContain('aria-label="4 việc cần xử lý"')
    expect(html).toContain("Còn 1 việc cần chú ý")
    expect(html).toContain('aria-label="Xem lời nhắc: Mốc 3"')
    expect(html).not.toContain('aria-label="Xem lời nhắc: Mốc 4"')
    expect(html).toContain("Đang tắt")
    expect(html).toContain("14 ngày")
    expect(html).toContain('href="/notifications/settings"')
  })

  it("shows the all-clear message only after a successful feed load", () => {
    expect(render()).toContain("Bạn đã xử lý hết các việc cần chú ý.")
    vi.mocked(useCachedQuery).mockReturnValue(state(null))
    const loading = render()
    expect(loading).toContain("Đang tải việc cần xử lý")
    expect(loading).not.toContain("Bạn đã xử lý hết")
    vi.mocked(useCachedQuery).mockReturnValue(
      state(
        null,
        new ApiError({
          status: 503,
          code: "UNAVAILABLE",
          message: "offline",
          traceId: "trace-123",
        }),
      ),
    )
    const failed = render()
    expect(failed).toContain("Chưa tải được việc cần xử lý.")
    expect(failed).toContain("trace-123")
    expect(failed).not.toContain("Bạn đã xử lý hết")
  })

  it("does not invent settings when the settings endpoint fails, and keeps its navigation link", () => {
    vi.mocked(useNotificationSettings).mockReturnValue(
      state(
        null,
        new ApiError({ status: 503, code: "UNAVAILABLE", message: "offline" }),
      ),
    )
    const html = render()
    expect(html).toContain("Chưa tải được cài đặt nhắc.")
    expect(html).not.toContain("Đang tắt")
    expect(html).not.toContain("Đang bật")
    expect(html).toContain("Điều chỉnh cài đặt")
  })

  it("identifies cached data when a refresh fails rather than showing an all-clear state", () => {
    const error = new ApiError({
      status: 503,
      code: "UNAVAILABLE",
      message: "offline",
    })
    vi.mocked(useCachedQuery).mockReturnValue(state([task("1")], error))
    vi.mocked(useNotificationSettings).mockReturnValue(
      state(settingsData, error),
    )
    const html = render()
    expect(html).toContain("Đang hiển thị lần tải trước.")
    expect(html).toContain("Chưa tải được việc cần xử lý.")
    expect(html).not.toContain("Bạn đã xử lý hết")
  })

  it("keeps the workshop feed separate and does not request owner settings", () => {
    const html = render("portal")
    expect(html).toContain("Không có việc chờ xử lý")
    expect(html).not.toContain("Tóm tắt và cài đặt thông báo")
    expect(useNotificationSettings).not.toHaveBeenCalled()
  })
})
