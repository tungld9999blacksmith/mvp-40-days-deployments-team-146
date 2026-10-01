import { newId } from '@/shared/utils/id'

const API_BASE = '/api/v1'

/** Error envelope of the backend: `{ "error": { code, message, details, traceId } }`. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown> | null
  readonly traceId: string | null
  /** Seconds from the `Retry-After` header or `details.retryAfterSeconds`. */
  readonly retryAfter: number | null

  constructor(init: {
    status: number
    code: string
    message: string
    details?: Record<string, unknown> | null
    traceId?: string | null
    retryAfter?: number | null
  }) {
    super(init.message)
    this.name = 'ApiError'
    this.status = init.status
    this.code = init.code
    this.details = init.details ?? null
    this.traceId = init.traceId ?? null
    this.retryAfter = init.retryAfter ?? null
  }

  /** `details.field` of validation errors, e.g. `phoneNumber` or `operatingHours[5].closeTime`. */
  get field(): string | null {
    const field = this.details?.field
    return typeof field === 'string' ? field : null
  }
}

export const NETWORK_ERROR = 'NETWORK_ERROR'
export const TIMEOUT_ERROR = 'TIMEOUT_ERROR'

export function isApiError(error: unknown): error is ApiError
/** Code check only — not a type guard, so the `false` branch keeps the original type. */
export function isApiError(error: unknown, code: string): boolean
export function isApiError(error: unknown, code?: string): boolean {
  return error instanceof ApiError && (code === undefined || error.code === code)
}

type TokenGetter = (forceRefresh: boolean) => Promise<string | null>

let getToken: TokenGetter = async () => null
let onUnauthorized: () => void = () => {}

/**
 * Wires the client to the active auth provider. The provider supplies the Firebase
 * ID token and the handler that ends the session when a request stays `401`.
 */
export function configureApiClient(options: { getToken: TokenGetter; onUnauthorized: () => void }) {
  getToken = options.getToken
  onUnauthorized = options.onUnauthorized
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
  /** Abort after this many milliseconds (client-side timeout). */
  timeoutMs?: number
  /** Send the Firebase ID token (default true). */
  auth?: boolean
  /** Do not end the session on a final 401 — the caller handles it (sign-in, logout). */
  skipSessionExpiry?: boolean
}

export interface ApiResponse<T> {
  data: T
  status: number
  headers: Headers
}

function parseRetryAfter(headers: Headers, details: Record<string, unknown> | null): number | null {
  const header = headers.get('Retry-After')
  if (header && /^\d+$/.test(header)) return Number(header)
  const fromDetails = details?.retryAfterSeconds
  return typeof fromDetails === 'number' ? fromDetails : null
}

async function toApiError(response: Response, requestId: string): Promise<ApiError> {
  const payload: unknown = await response.json().catch(() => null)
  const traceId = response.headers.get('X-Trace-Id') ?? response.headers.get('X-Request-ID') ?? requestId

  if (payload && typeof payload === 'object' && 'error' in payload) {
    const body = (payload as { error: Record<string, unknown> }).error ?? {}
    const details = (body.details as Record<string, unknown> | null) ?? null
    return new ApiError({
      status: response.status,
      code: typeof body.code === 'string' ? body.code : `HTTP_${response.status}`,
      message: typeof body.message === 'string' ? body.message : response.statusText,
      details,
      traceId: typeof body.traceId === 'string' ? body.traceId : traceId,
      retryAfter: parseRetryAfter(response.headers, details),
    })
  }

  // FastAPI default errors: `{ "detail": ... }` (token check, request validation).
  const detail = payload && typeof payload === 'object' && 'detail' in payload
    ? (payload as { detail: unknown }).detail
    : null
  const code =
    response.status === 401 ? 'UNAUTHORIZED'
    : response.status === 422 || response.status === 400 ? 'INVALID_REQUEST'
    : response.status >= 500 ? 'INTERNAL_SERVER_ERROR'
    : `HTTP_${response.status}`
  return new ApiError({
    status: response.status,
    code,
    message: typeof detail === 'string' ? detail : response.statusText,
    traceId,
    retryAfter: parseRetryAfter(response.headers, null),
  })
}

function withTimeout(signal: AbortSignal | undefined, timeoutMs: number | undefined) {
  if (!timeoutMs) return { signal, cleanup: () => {}, timedOut: () => false }
  const controller = new AbortController()
  let didTimeout = false
  const timer = setTimeout(() => {
    didTimeout = true
    controller.abort()
  }, timeoutMs)
  const onAbort = () => controller.abort()
  signal?.addEventListener('abort', onAbort)
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
    },
    timedOut: () => didTimeout,
  }
}

/** Builds headers, performs fetch, retries once on 401 with a refreshed token. */
export async function rawRequest(path: string, options: RequestOptions = {}): Promise<{ response: Response; requestId: string }> {
  const requestId = newId()
  const useAuth = options.auth !== false

  const send = async (forceRefresh: boolean) => {
    const headers = new Headers(options.headers)
    headers.set('X-Request-ID', requestId)
    if (!headers.has('Accept')) headers.set('Accept', 'application/json')
    if (options.body !== undefined && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
    if (useAuth) {
      const token = await getToken(forceRefresh)
      if (token) headers.set('Authorization', `Bearer ${token}`)
    }

    const timeout = withTimeout(options.signal, options.timeoutMs)
    try {
      return await fetch(`${API_BASE}${path}`, {
        method: options.method ?? 'GET',
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: timeout.signal,
      })
    } catch (error) {
      if (timeout.timedOut()) {
        throw new ApiError({ status: 0, code: TIMEOUT_ERROR, message: 'Request timed out', traceId: requestId })
      }
      if (error instanceof DOMException && error.name === 'AbortError') throw error
      throw new ApiError({ status: 0, code: NETWORK_ERROR, message: 'Network error', traceId: requestId })
    } finally {
      timeout.cleanup()
    }
  }

  let response: Response
  try {
    response = await send(false)
    if (response.status === 401 && useAuth) {
      response = await send(true)
    }
  } catch (error) {
    // Refreshing the token itself failed (revoked / disabled account): the session is over.
    if (!(error instanceof ApiError) && !(error instanceof DOMException)) {
      if (useAuth && !options.skipSessionExpiry) onUnauthorized()
      throw new ApiError({ status: 401, code: 'UNAUTHORIZED', message: 'Session expired', traceId: requestId })
    }
    throw error
  }

  if (response.status === 401 && useAuth && !options.skipSessionExpiry) {
    onUnauthorized()
  }
  return { response, requestId }
}

/** JSON request against FastAPI. Unwraps `{ data }`, returns `undefined` data for 204. */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
  const { response, requestId } = await rawRequest(path, options)
  if (!response.ok) throw await toApiError(response, requestId)

  if (response.status === 204) {
    return { data: undefined as T, status: 204, headers: response.headers }
  }
  const payload: unknown = await response.json().catch(() => null)
  const data =
    payload && typeof payload === 'object' && 'data' in payload
      ? (payload as { data: T }).data
      : (payload as T)
  return { data, status: response.status, headers: response.headers }
}

export async function apiGet<T>(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
  return (await apiRequest<T>(path, { ...options, method: 'GET' })).data
}

export interface PageInfo {
  nextCursor: string | null
  hasMore: boolean
}

/** Paged list: `{ "data": [...], "page": { nextCursor, hasMore } }` (platform API §1.2). */
export async function apiGetPaged<T>(
  path: string,
  options: Omit<RequestOptions, 'method' | 'body'> = {},
): Promise<{ data: T[]; page: PageInfo }> {
  const { response, requestId } = await rawRequest(path, { ...options, method: 'GET' })
  if (!response.ok) throw await toApiError(response, requestId)
  const payload = (await response.json().catch(() => null)) as { data?: T[]; page?: Partial<PageInfo> } | null
  return {
    data: payload?.data ?? [],
    page: { nextCursor: payload?.page?.nextCursor ?? null, hasMore: payload?.page?.hasMore ?? false },
  }
}

export { toApiError }
