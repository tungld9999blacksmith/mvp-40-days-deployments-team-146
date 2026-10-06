/**
 * Mock API server for endpoints the backend does not expose yet (us-033/037/041/045/049/053/057).
 * It answers inside `rawRequest` with real `Response` objects in the backend envelope, so the
 * feature `api.ts` modules are the same code that will talk to the real API later.
 *
 * Three hooks per route:
 * - `route`    answers a request (return `undefined` to let it reach the real backend);
 * - `rewrite`  changes the body of a request that still goes to the real backend;
 * - `observe`  learns from a successful real response (workshops, vehicles, created bookings).
 */
import { getDb, save } from './db'

export type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface MockRequest {
  method: Method
  path: string
  params: Record<string, string>
  query: URLSearchParams
  body: unknown
  headers: Headers
}

export interface MockResult {
  status: number
  body?: unknown
  headers?: Record<string, string>
  /** Raw payload (e.g. a PNG blob) instead of JSON. */
  raw?: BodyInit
  contentType?: string
}

type Handler = (req: MockRequest) => MockResult | undefined | Promise<MockResult | undefined>
type Rewriter = (req: MockRequest) => unknown
type Observer = (req: MockRequest, data: unknown) => void

interface Entry<T> {
  method: Method
  group: string
  pattern: RegExp
  keys: string[]
  fn: T
}

const routes: Entry<Handler>[] = []
const rewriters: Entry<Rewriter>[] = []
const observers: Entry<Observer>[] = []

function compile(path: string): { pattern: RegExp; keys: string[] } {
  const keys: string[] = []
  const source = path.replace(/:([A-Za-z]+)/g, (_, key: string) => {
    keys.push(key)
    return '([^/]+)'
  })
  return { pattern: new RegExp(`^${source}$`), keys }
}

export function route(group: string, method: Method, path: string, fn: Handler) {
  routes.push({ method, group, fn, ...compile(path) })
}

export function rewrite(group: string, method: Method, path: string, fn: Rewriter) {
  rewriters.push({ method, group, fn, ...compile(path) })
}

export function observe(group: string, method: Method, path: string, fn: Observer) {
  observers.push({ method, group, fn, ...compile(path) })
}

function match<T>(list: Entry<T>[], method: string, pathname: string, enabled: (group: string) => boolean) {
  const found: { entry: Entry<T>; params: Record<string, string> }[] = []
  for (const entry of list) {
    if (entry.method !== method || !enabled(entry.group)) continue
    const result = entry.pattern.exec(pathname)
    if (!result) continue
    const params: Record<string, string> = {}
    entry.keys.forEach((key, index) => {
      params[key] = decodeURIComponent(result[index + 1])
    })
    found.push({ entry, params })
  }
  return found
}

function split(path: string): { pathname: string; query: URLSearchParams } {
  const [pathname, search = ''] = path.split('?')
  return { pathname, query: new URLSearchParams(search) }
}

export interface RequestInfo {
  method: Method
  path: string
  body: unknown
  headers: Headers
}

/** First matching route that answers, or `null` to let the request reach the backend. */
export async function handle(info: RequestInfo, enabled: (group: string) => boolean): Promise<Response | null> {
  const { pathname, query } = split(info.path)
  for (const { entry, params } of match(routes, info.method, pathname, enabled)) {
    const result = await entry.fn({ ...info, params, query })
    if (!result) continue
    // Realistic latency in the browser (loading states stay visible); none in unit tests.
    if (typeof window !== 'undefined') await new Promise(resolve => setTimeout(resolve, 120 + Math.random() * 280))
    const headers = new Headers(result.headers)
    headers.set('X-Mock-Api', entry.group)
    if (result.raw !== undefined) {
      headers.set('Content-Type', result.contentType ?? 'application/octet-stream')
      return new Response(result.raw, { status: result.status, headers })
    }
    if (result.status === 204) return new Response(null, { status: 204, headers })
    headers.set('Content-Type', 'application/json')
    return new Response(JSON.stringify(result.body ?? null), { status: result.status, headers })
  }
  return null
}

export function rewriteBody(info: RequestInfo, enabled: (group: string) => boolean): unknown {
  const { pathname, query } = split(info.path)
  let body = info.body
  for (const { entry, params } of match(rewriters, info.method, pathname, enabled)) {
    body = entry.fn({ ...info, body, params, query })
  }
  return body
}

export async function observeResponse(info: RequestInfo, response: Response, enabled: (group: string) => boolean) {
  const { pathname, query } = split(info.path)
  const found = match(observers, info.method, pathname, enabled)
  if (found.length === 0) return
  const payload: unknown = await response.clone().json().catch(() => null)
  const data = payload && typeof payload === 'object' && 'data' in payload ? (payload as { data: unknown }).data : payload
  for (const { entry, params } of found) {
    try {
      entry.fn({ ...info, params, query }, data)
    } catch (error) {
      console.warn('[mock-api] observer failed', error)
    }
  }
}

// ---------------------------------------------------------------- response helpers

export function ok(data: unknown, status = 200): MockResult {
  return { status, body: { data } }
}

export function noContent(): MockResult {
  return { status: 204 }
}

export function fail(status: number, code: string, message: string, details: Record<string, unknown> | null = null): MockResult {
  return { status, body: { error: { code, message, details, traceId: `mock-${Math.random().toString(16).slice(2, 10)}` } } }
}

export function bodyOf<T extends object>(req: MockRequest): Partial<T> {
  return (req.body && typeof req.body === 'object' ? req.body : {}) as Partial<T>
}

/** Response stored for this `Idempotency-Key`, replayed on a retry. */
export function replayIdempotent(req: MockRequest): MockResult | null {
  const key = req.headers.get('Idempotency-Key')
  const stored = key ? getDb().idempotency[`${req.path}:${key}`] : undefined
  return stored ? { status: stored.status, body: stored.body } : null
}

/** Stores the response of this `Idempotency-Key` (and saves the db). */
export function rememberIdempotent(req: MockRequest, result: MockResult): MockResult {
  const key = req.headers.get('Idempotency-Key')
  if (key) getDb().idempotency[`${req.path}:${key}`] = { status: result.status, body: result.body }
  save()
  return result
}
