import { describe, expect, it } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { MemoryRouter } from "react-router-dom"
import BookingProposalCard, { proposalLink } from "../assistant/components/DemoBookingProposalCard"
import { ticketToBooking } from "./ticket"

describe("agent proposal and ticket", () => {
  it("opens server proposal recheck without creating a booking", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <BookingProposalCard
          card={{
            type: "booking_proposal",
            proposalId: "p/1",
            workshopName: "Demo workshop",
            date: "2026-10-05",
            timeSlot: "14:00:00",
            estimatedCost: 400000,
          }}
        />
      </MemoryRouter>,
    )
    expect(proposalLink({ type: "booking_proposal", proposalId: "p/1" })).toBe("/booking/proposal?proposalId=p%2F1")
    expect(html).toContain("Xác nhận đặt lịch")
    expect(html).toContain("chưa giữ chỗ")
    expect(html).toContain("400.000")
  })
  it("ignores unsupported card types", () => {
    expect(
      renderToStaticMarkup(<BookingProposalCard card={{ type: "unknown" }} />),
    ).toBe("")
  })
  it("reads workshop and cost from API ticket without navigation state", () => {
    const booking = ticketToBooking({
      bookingId: "b1",
      status: "confirmed",
      bookingDate: "2026-10-05",
      timeSlot: "14:00:00",
      workshop: { workshopId: "w1", name: "Workshop" },
      cost: { amount: 400000 },
    })
    expect(booking.workshopName).toBe("Workshop")
    expect(booking.workshopId).toBe("w1")
    expect(booking.estimatedCost).toBe(400000)
    expect(booking.ownerCancelableUntil).toBeNull()
  })
})
