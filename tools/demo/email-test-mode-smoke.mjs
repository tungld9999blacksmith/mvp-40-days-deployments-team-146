// Firebase Emulator + UI + isolated demo backend. Run only against the recording transport fixture.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { chromium } from '@playwright/test'
import { completeRegistration } from './registration-fixture.mjs'

const base = process.env.DEMO_FRONTEND_URL || 'http://127.0.0.1:5174'
const recipient = process.env.DEMO_EMAIL_TEST_TO
if (!recipient?.endsWith('@example.com')) throw new Error('This UI regression requires a synthetic example.com recipient')
const runId = `email-test-mode-${Date.now()}`
const artifacts = path.resolve(process.env.DEMO_EMAIL_TEST_ARTIFACTS || 'artifacts/email-test-mode')
const browser = await chromium.launch({ channel: process.env.DEMO_BROWSER_CHANNEL || 'chrome', headless: true })
const contexts = []
const created = []
const checks = []
const errors = []
let failure = null

async function api(page, endpoint, method = 'GET', body) {
  return page.evaluate(async ({ endpoint, method, body }) => {
    const { getIdToken } = await import('/src/features/auth/firebase.ts')
    const response = await fetch(`/api/v1${endpoint}`, {
      method,
      headers: { Authorization: `Bearer ${await getIdToken()}`, 'Content-Type': 'application/json' },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })
    return { status: response.status, ...(await response.json()) }
  }, { endpoint, method, body })
}

async function signIn(email, suffix) {
  const context = await browser.newContext()
  contexts.push(context)
  const page = await context.newPage()
  page.setDefaultTimeout(30_000)
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(base)
  const isNew = await page.evaluate(async ({ email, uid }) => {
    const { getFirebaseAuth } = await import('/src/features/auth/firebase.ts')
    const { setPortal } = await import('/src/features/auth/portal.ts')
    const { GoogleAuthProvider, signInWithCredential, getAdditionalUserInfo } = await import('/node_modules/.vite/deps/firebase_auth.js')
    const auth = getFirebaseAuth()
    if (!auth?.emulatorConfig) throw new Error('Requires Firebase Auth Emulator')
    setPortal('owner')
    const result = await signInWithCredential(auth, GoogleAuthProvider.credential(JSON.stringify({
      sub: uid, email, email_verified: true, name: 'Chủ xe thử giao diện',
    })))
    return getAdditionalUserInfo(result)?.isNewUser === true
  }, { email, uid: `${runId}-${suffix}` })
  assert.equal(isNew, true, 'Refuse to reuse/delete an existing account')
  created.push(page)
  await page.waitForURL(url => url.pathname.startsWith('/onboarding/') || url.pathname === '/dashboard')
  await completeRegistration(page)
  return page
}

try {
  const owner = await signIn(recipient, 'owner')
  const initial = await api(owner, '/notification-settings')
  assert.equal(initial.data.emailTransport, 'resend_test')
  assert.equal(initial.data.emailTestRecipientMatched, true)
  assert.equal((await api(owner, '/notifications/email-outbox')).data.items.length, 0)
  await owner.goto(`${base}/notifications/settings`)
  await owner.getByRole('switch', { name: 'Bật nhắc bảo dưỡng' }).click()
  await owner.locator('#channel-EMAIL label').click()
  const save = owner.waitForResponse(r => r.url().endsWith('/notification-settings') && r.request().method() === 'PUT')
  await owner.getByRole('button', { name: 'Lưu', exact: true }).click()
  assert.equal((await save).status(), 200)
  await owner.getByRole('link', { name: 'Mở email demo và gửi thử', exact: true }).click()
  const send = owner.getByRole('button', { name: 'Gửi thử email thật', exact: true })
  await send.waitFor()
  // Verify the fixture before the button can perform any I/O to a real provider.
  assert.equal((await api(owner, '/demo/email-test-fixture')).data.transport, 'recording')
  for (let attempt = 0; attempt < 2; attempt++) {
    const response = owner.waitForResponse(r => r.url().endsWith('/demo/email-test/send'))
    await send.click()
    assert.equal((await response).status(), 200)
    await owner.getByText('Resend đã tiếp nhận', { exact: false }).waitFor()
  }
  let inbox = (await api(owner, '/notifications/email-outbox')).data
  assert.equal(inbox.items.length, 1)
  assert.ok(inbox.items[0].payload.subject.startsWith('[DEMO]'))
  assert.equal(inbox.items[0].attempts, 1)
  assert.equal((await api(owner, '/demo/email-test-fixture')).data.sendCount, 1)
  checks.push('UI opt-in, explicit send, [DEMO] label and repeated clicks create one recording transport call')
  await owner.getByRole('link', { name: 'Xem lời nhắc và hành động', exact: true }).click()
  await owner.getByText('Email thử thật [DEMO]', { exact: false }).waitFor()
  checks.push('Reminder detail identifies the real test email')
  await owner.goto(`${base}/notifications/settings`)
  await owner.locator('#channel-EMAIL label').click()
  const disable = owner.waitForResponse(r => r.url().endsWith('/notification-settings') && r.request().method() === 'PUT')
  await owner.getByRole('button', { name: 'Lưu', exact: true }).click()
  assert.equal((await disable).status(), 200)
  await owner.getByRole('link', { name: 'Mở email demo và gửi thử', exact: true }).click()
  const rejected = owner.waitForResponse(r => r.url().endsWith('/demo/email-test/send'))
  await owner.getByRole('button', { name: 'Gửi thử email thật', exact: true }).click()
  assert.equal((await rejected).status(), 422)
  assert.equal((await api(owner, '/demo/email-test-fixture')).data.sendCount, 1)
  checks.push('UI opt-out prevents sending')
  const other = await signIn(`${runId}-other@example.com`, 'other')
  await other.goto(`${base}/notifications/demo-email`)
  await other.getByText('Tài khoản demo cần dùng email trùng địa chỉ gửi thử đã cấu hình.').waitFor()
  assert.equal(await other.getByRole('button', { name: 'Gửi thử email thật', exact: true }).count(), 0)
  inbox = (await api(other, '/notifications/email-outbox')).data
  assert.equal(inbox.items.length, 0)
  assert.equal((await api(other, '/demo/email-test/send', 'POST', {})).status, 403)
  checks.push('Other emulator accounts cannot send or read the owner email')
  assert.deepEqual(errors, [])
} catch (error) {
  failure = error instanceof Error ? error.message : String(error)
} finally {
  for (const page of created) {
    await page.evaluate(async () => {
      const { getFirebaseAuth } = await import('/src/features/auth/firebase.ts')
      await getFirebaseAuth()?.currentUser?.delete()
    }).catch(() => {})
  }
  for (const context of contexts) await context.close()
  await browser.close()
  await mkdir(artifacts, { recursive: true })
  await writeFile(path.join(artifacts, 'report.json'), JSON.stringify({
    transport: 'recording', realEmailsSent: 0, checks, browserErrors: errors, failure,
  }, null, 2))
}
for (const check of checks) console.log(`PASS: ${check}`)
if (failure) throw new Error(failure)
