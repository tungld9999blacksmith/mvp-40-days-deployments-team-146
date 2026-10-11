import { apiGet, apiRequest } from '@/shared/api/client'
import type { Decision, LinesView, PhotoUploadTarget, ProposeExtraRequest } from './types'

const id = (value: string) => encodeURIComponent(value)
const WS = '/workshop-owner'

// ── vehicle owner ───────────────────────────────────────────────────────────
export function getMyBookingLines(bookingId: string): Promise<LinesView> {
  return apiGet<LinesView>(`/bookings/${id(bookingId)}/lines`, { timeoutMs: 10_000 })
}

/** The only way a line is approved or declined; `seenVersion` = the version on screen. */
export async function decideLine(
  bookingId: string,
  lineId: string,
  body: { decision: Decision; seenVersion: number; confirmSafety?: boolean },
): Promise<LinesView> {
  return (await apiRequest<LinesView>(`/bookings/${id(bookingId)}/lines/${id(lineId)}/decision`, { method: 'POST', body, timeoutMs: 15_000 })).data
}

/** "Tôi không đồng ý": a decision the workshop recorded by phone goes back to the owner. */
export async function disputeLine(bookingId: string, lineId: string, seenVersion: number): Promise<LinesView> {
  return (await apiRequest<LinesView>(`/bookings/${id(bookingId)}/lines/${id(lineId)}/dispute`, { method: 'POST', body: { seenVersion }, timeoutMs: 15_000 })).data
}

// ── workshop owner ──────────────────────────────────────────────────────────
export function getWorkshopBookingLines(bookingId: string): Promise<LinesView> {
  return apiGet<LinesView>(`${WS}/bookings/${id(bookingId)}/lines`, { timeoutMs: 10_000 })
}

export async function confirmPackageLine(
  bookingId: string,
  lineId: string,
  body: { expectedVersion: number; price: number; reason?: string },
): Promise<LinesView> {
  return (await apiRequest<LinesView>(`${WS}/bookings/${id(bookingId)}/lines/${id(lineId)}/confirm`, { method: 'POST', body, timeoutMs: 15_000 })).data
}

export async function proposeExtra(bookingId: string, body: ProposeExtraRequest): Promise<LinesView> {
  return (await apiRequest<LinesView>(`${WS}/bookings/${id(bookingId)}/lines`, { method: 'POST', body, timeoutMs: 20_000 })).data
}

export async function editLine(
  bookingId: string,
  lineId: string,
  body: { expectedVersion: number; price: number; reason?: string },
): Promise<LinesView> {
  return (await apiRequest<LinesView>(`${WS}/bookings/${id(bookingId)}/lines/${id(lineId)}`, { method: 'PATCH', body, timeoutMs: 15_000 })).data
}

/** The owner answered by phone; they are told at once and can dispute it until COMPLETE. */
export async function recordPhoneDecision(
  bookingId: string,
  lineId: string,
  body: { decision: Decision; seenVersion: number; confirmedByName: string; confirmSafety?: boolean },
): Promise<LinesView> {
  return (await apiRequest<LinesView>(`${WS}/bookings/${id(bookingId)}/lines/${id(lineId)}/phone-decision`, { method: 'POST', body, timeoutMs: 15_000 })).data
}

export async function withdrawLine(bookingId: string, lineId: string, expectedVersion: number): Promise<LinesView> {
  return (
    await apiRequest<LinesView>(`${WS}/bookings/${id(bookingId)}/lines/${id(lineId)}/withdraw`, {
      method: 'POST',
      body: { expectedVersion },
      timeoutMs: 15_000,
    })
  ).data
}

export async function signLinePhotoUpload(bookingId: string, contentType: string): Promise<PhotoUploadTarget> {
  return (await apiRequest<PhotoUploadTarget>(`${WS}/bookings/${id(bookingId)}/line-photos`, { method: 'POST', body: { contentType }, timeoutMs: 10_000 })).data
}

/** PUT the file to the signed URL (private bucket) and report progress 0..1. */
export function uploadPhoto(target: PhotoUploadTarget, file: File, onProgress: (ratio: number) => void, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', target.uploadUrl)
    xhr.setRequestHeader('Content-Type', file.type)
    xhr.setRequestHeader('x-upsert', 'false')
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) onProgress(event.loaded / event.total)
    }
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`upload ${xhr.status}`)))
    xhr.onerror = () => reject(new Error('upload network error'))
    xhr.onabort = () => reject(new DOMException('aborted', 'AbortError'))
    signal?.addEventListener('abort', () => xhr.abort())
    xhr.send(file)
  })
}
