import { apiGet, apiRequest } from '@/shared/api/client'
import type { FollowUp, FollowUpResult } from './types'

const enc = encodeURIComponent

/** API-FU-01 */
export function getFollowUp(followUpId: string): Promise<FollowUp> {
  return apiGet<FollowUp>(`/follow-ups/${enc(followUpId)}`, { timeoutMs: 10_000 })
}

/** API-FU-02 — classification may take ~6 s: no client timeout below 10 s (§9). */
export async function respondFollowUp(followUpId: string, body: { rating: number; comment: string | null }): Promise<FollowUpResult> {
  return (await apiRequest<FollowUpResult>(`/follow-ups/${enc(followUpId)}/response`, { method: 'POST', body, timeoutMs: 20_000 })).data
}
