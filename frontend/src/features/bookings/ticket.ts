import type { Booking } from "./types"

export type TicketResponse = Partial<Booking> & Pick<Booking, "bookingId" | "status" | "bookingDate" | "timeSlot"> & {
  workshop: { workshopId: string; name: string; address?: string }
  cost: { amount: number | string | null }
  actualCost?: number | null
  history?: { toStatus: string; at: string; note?: string | null }[]
}

export function ticketToBooking(ticket: TicketResponse): Booking {
  return {
    bookingId: ticket.bookingId,
    status: ticket.status,
    bookingDate: ticket.bookingDate,
    timeSlot: ticket.timeSlot,
    workshopId: ticket.workshop.workshopId,
    workshopName: ticket.workshop.name,
    confirmationMode: ticket.confirmationMode ?? "",
    bookingCode: ticket.bookingCode ?? null,
    estimatedCost: ticket.estimatedCost ?? ticket.cost.amount,
    estimateLabel: ticket.estimateLabel ?? "Chi phí ước tính",
    ownerCancelableUntil: ticket.ownerCancelableUntil ?? null,
    holdExpiresAt: ticket.holdExpiresAt ?? null,
    qrUrl: ticket.qrUrl ?? null,
    quoteId: ticket.quoteId ?? null,
  }
}
