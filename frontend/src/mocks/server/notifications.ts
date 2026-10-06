/**
 * Demo mode: reminder settings and the in-app feed (us-021 API-NOTI-001 → 003). Like the backend,
 * the feed has no table of its own: it is derived from the vehicle due status, the owner's booking
 * events and the post-service surveys.
 */
import { visibleCode } from './bookings'
import { bodyOf, fail, ok, route } from './core'
import { getDb, save, type MockBooking } from './db'
import { dueOf, ownerVehicle } from './vehicles'

const GROUP = 'notifications'
const DEFAULT_LEAD_DAYS = 7
const FEED_DAYS = 90
const CHANNELS = ['ZALO', 'TELEGRAM', 'SMS', 'EMAIL']
const OPEN_STATES = ['pending', 'confirmed', 'checked_in', 'in_progress']
const FEED_STATUSES: Record<string, 'CONFIRMED' | 'CANCELLED' | 'COMPLETED'> = {
  CONFIRMED: 'CONFIRMED',
  CANCELLED: 'CANCELLED',
  COMPLETED: 'COMPLETED',
}

function settingsView() {
  const settings = getDb().notificationSettings
  return {
    remindersEnabled: settings.remindersEnabled,
    reminderLeadDays: settings.reminderLeadDays,
    defaultReminderLeadDays: DEFAULT_LEAD_DAYS,
    // External channels are not built yet: in-app only ("Sắp có").
    channels: CHANNELS.map(channel => ({ channel, enabled: false, available: false, status: 'COMING_SOON' })),
  }
}

function reminderItem() {
  const vehicle = ownerVehicle()
  const settings = getDb().notificationSettings
  if (!vehicle || !settings.remindersEnabled) return null
  const due = dueOf(vehicle)
  if (due.dueStatus !== 'DUE_SOON' && due.dueStatus !== 'OVERDUE') return null
  const days = due.remainingDays ?? 0
  const level = due.dueStatus === 'OVERDUE' ? 'EXPIRED' : days <= 3 ? 'URGENT' : days <= 7 ? 'WARNING' : 'EARLY'
  const resolved = getDb().bookings.some(
    booking => booking.userVehicleId === vehicle.userVehicleId && booking.odoMilestone === due.nextKm && OPEN_STATES.includes(booking.status),
  )
  const today = new Date()
  today.setHours(8, 0, 0, 0)
  return {
    id: `reminder:${vehicle.userVehicleId}:${due.nextKm}`,
    kind: 'MAINTENANCE_REMINDER' as const,
    occurredAt: today.toISOString(),
    unread: false,
    reminder: { userVehicleId: vehicle.userVehicleId, level, odoMilestoneKm: due.nextKm!, resolved },
    booking: null,
    followUp: null,
  }
}

function bookingItems(booking: MockBooking) {
  const workshop = getDb().workshops.find(item => item.workshopId === booking.workshopId)
  return booking.events
    .filter(event => FEED_STATUSES[event.toStatus] && event.actorType !== 'VEHICLE_OWNER')
    .map(event => ({
      id: `booking:${booking.bookingId}:${event.toStatus}:${event.at}`,
      kind: 'BOOKING_UPDATE' as const,
      occurredAt: event.at,
      unread: false,
      reminder: null,
      booking: {
        bookingId: booking.bookingId,
        bookingCode: visibleCode(booking) ?? 'Yêu cầu đặt lịch',
        status: FEED_STATUSES[event.toStatus],
        reasonCode: event.reasonCode,
        bookingDate: booking.bookingDate,
        timeSlot: booking.timeSlot,
        workshopName: workshop?.name ?? null,
      },
      followUp: null,
    }))
}

function followUpItems() {
  const db = getDb()
  return db.followUps
    .filter(followUp => followUp.status !== 'pending' && followUp.sentAt)
    .map(followUp => {
      const booking = db.bookings.find(item => item.bookingId === followUp.bookingId)
      if (!booking?.ownerSelf) return null
      const workshop = db.workshops.find(item => item.workshopId === booking.workshopId)
      return {
        id: `follow-up:${followUp.followUpId}`,
        kind: 'FOLLOW_UP' as const,
        occurredAt: followUp.sentAt!,
        unread: followUp.status === 'sent' && !followUp.response,
        reminder: null,
        booking: null,
        followUp: { followUpId: followUp.followUpId, bookingId: booking.bookingId, workshopName: workshop?.name ?? null },
      }
    })
    .filter(item => item !== null)
}

export function registerNotificationRoutes() {
  route(GROUP, 'GET', '/notification-settings', () => ok(settingsView()))

  route(GROUP, 'PUT', '/notification-settings', req => {
    const body = bodyOf<{ remindersEnabled: boolean; reminderLeadDays: number }>(req)
    const settings = getDb().notificationSettings
    if (body.reminderLeadDays !== undefined) {
      if (!Number.isInteger(body.reminderLeadDays) || body.reminderLeadDays < 0 || body.reminderLeadDays > 30) {
        return fail(400, 'INVALID_REQUEST', 'Số ngày nhắc trước phải từ 0 đến 30.', { field: 'reminderLeadDays' })
      }
      settings.reminderLeadDays = body.reminderLeadDays
    }
    if (typeof body.remindersEnabled === 'boolean') settings.remindersEnabled = body.remindersEnabled
    save()
    return ok(settingsView())
  })

  route(GROUP, 'GET', '/notifications', () => {
    const since = Date.now() - FEED_DAYS * 86_400_000
    const own = getDb().bookings.filter(booking => booking.ownerSelf)
    const items = [reminderItem(), ...own.flatMap(bookingItems), ...followUpItems()]
      .filter(item => item !== null)
      .filter(item => new Date(item.occurredAt).getTime() >= since)
      .sort((a, b) => b.occurredAt.localeCompare(a.occurredAt))
    return ok({ items, unreadCount: items.filter(item => item.unread).length })
  })
}
