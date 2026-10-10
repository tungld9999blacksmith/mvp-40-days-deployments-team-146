// Real browser + Firebase Auth Emulator + demo backend; emails stay in the mock outbox.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { chromium } from '@playwright/test'
import { completeRegistration } from './registration-fixture.mjs'

const base = process.env.DEMO_FRONTEND_URL || 'http://127.0.0.1:5174'
const artifacts = path.resolve(process.env.DEMO_EMAIL_TEST_ARTIFACTS || 'artifacts/email-reminder-smoke')
const runId = `email-reminder-${Date.now()}`
const results = []
const llmTurns = []
const browserErrors = []
const contexts = []
const testUsers = []
const useLlm = process.env.DEMO_EMAIL_TEST_LLM === 'on'
const demoNow = process.env.DEMO_EMAIL_TEST_NOW
const workshopEmail = process.env.DEMO_EMAIL_TEST_WORKSHOP_EMAIL || 'email-reminder-workshop@example.com'
await mkdir(artifacts, { recursive: true })
const browser = await chromium.launch({ channel: process.env.DEMO_BROWSER_CHANNEL || 'chrome', headless: true })
let page
let failure = null

function passed(name, details = {}) {
  results.push({ name, passed: true, ...details })
  console.log(`PASS: ${name}`)
}

async function signIn(suffix, portal = 'owner') {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  contexts.push(context)
  const tab = await context.newPage()
  if (demoNow) await tab.clock.setFixedTime(new Date(demoNow))
  tab.setDefaultTimeout(30000)
  tab.on('pageerror', error => browserErrors.push(error.message))
  await tab.goto(portal === 'workshop' ? `${base}/workshop/login` : base)
  const email = portal === 'workshop' ? workshopEmail : `${runId}-${suffix}@example.com`
  const identity = await tab.evaluate(async ({ uid, email, portal }) => {
    const { getFirebaseAuth } = await import('/src/features/auth/firebase.ts')
    const { setPortal } = await import('/src/features/auth/portal.ts')
    const { GoogleAuthProvider, signInWithCredential, getAdditionalUserInfo } = await import('/node_modules/.vite/deps/firebase_auth.js')
    const auth = getFirebaseAuth()
    if (!auth?.emulatorConfig) throw new Error('This test requires Firebase Auth Emulator')
    setPortal(portal)
    const result = await signInWithCredential(auth, GoogleAuthProvider.credential(JSON.stringify({
      sub: uid, email, email_verified: true, name: 'Chủ xe thử email',
    })))
    return { uid: result.user.uid, email: result.user.email, isNewUser: getAdditionalUserInfo(result)?.isNewUser }
  }, { uid: `${runId}-${suffix}`, email, portal })
  assert.equal(identity.email, email)
  assert.equal(identity.isNewUser, true, 'Refuse to reuse or later delete an existing account')
  testUsers.push({ tab, ...identity })
  await tab.waitForURL(url => portal === 'workshop'
    ? url.pathname === '/technician' || url.pathname.startsWith('/workshop/onboarding/')
    : ['/dashboard', '/onboarding/profile', '/onboarding/vehicle'].includes(url.pathname))
  await completeRegistration(tab, portal)
  return tab
}

async function api(tab, endpoint, method = 'GET', body, expectedStatus = 200) {
  const response = await tab.evaluate(async ({ endpoint, method, body }) => {
    const { getIdToken } = await import('/src/features/auth/firebase.ts')
    const response = await fetch(`/api/v1${endpoint}`, {
      method, headers: { Authorization: `Bearer ${await getIdToken()}`, 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
    return { status: response.status, body: await response.json() }
  }, { endpoint, method, body })
  assert.equal(response.status, expectedStatus, `HTTP status for ${method} ${endpoint}`)
  return response.body.data ?? response.body
}

async function screenshot(name) {
  await page.screenshot({ path: path.join(artifacts, `${name}.png`), fullPage: true, animations: 'disabled' })
}

async function scan() {
  const response = page.waitForResponse(r => r.url().endsWith('/api/v1/demo/reminders/run') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Kiểm tra mốc ngay', exact: true }).click()
  assert.equal((await response).status(), 200)
  await page.getByRole('button', { name: 'Kiểm tra mốc ngay', exact: true }).waitFor({ state: 'visible' })
}

async function ask(question, expectedTool) {
  await page.getByRole('textbox', { name: 'Nhập câu hỏi' }).fill(question)
  const response = page.waitForResponse(r => r.url().includes('/messages') && r.request().method() === 'POST', { timeout: 150000 })
  await page.getByRole('button', { name: 'Gửi', exact: true }).click()
  const stream = await (await response).text()
  const events = stream.split(/\r?\n\r?\n/).map(block => {
    const name = block.match(/^event: (.+)$/m)?.[1]
    const raw = block.match(/^data: (.+)$/m)?.[1]
    if (!name || !raw) return null
    return { event: name, data: JSON.parse(raw) }
  }).filter(Boolean)
  llmTurns.push({
    question,
    expectedTool,
    tools: events.filter(event => event.event === 'status' && event.data.tool).map(event => event.data.tool),
    answer: events.findLast(event => event.event === 'message.completed')?.data.message?.content ?? null,
    errors: events.filter(event => event.event === 'error').map(event => event.data.code),
  })
  assert.ok(stream.includes('event: message.completed'), 'Agent turn must complete')
  assert.ok(!stream.includes('event: error'), 'Agent turn must not report an error')
  assert.ok(stream.includes(expectedTool), `Agent must call ${expectedTool}`)
  await page.getByRole('button', { name: 'Gửi', exact: true }).waitFor({ state: 'visible' })
  return stream
}

async function bookFromReminder(reminderId, vehicleId, milestone) {
  await page.goto(`${base}/notifications/reminders/${reminderId}`)
  await page.getByRole('link', { name: 'Đặt lịch theo mốc hiện tại', exact: true }).click()
  await page.waitForURL(url => url.pathname === '/booking')
  assert.equal(new URL(page.url()).searchParams.get('userVehicleId'), vehicleId)
  assert.equal(new URL(page.url()).searchParams.get('odoMilestone'), String(milestone))
  await page.getByRole('button', { name: /Tự chọn xưởng & giờ/ }).click()
  await page.getByRole('button', { name: /Xưởng demo EV Care 1/ }).click()
  await page.getByRole('radiogroup', { name: 'Khung giờ', exact: true })
    .locator('[role="radio"]:not(:disabled)').first().click()
  await page.waitForURL('**/booking/confirm?**')
  assert.equal(new URL(page.url()).searchParams.get('userVehicleId'), vehicleId)
  await page.getByRole('button', { name: 'Xác nhận', exact: true }).click()
  await page.waitForURL('**/bookings/**')
  return new URL(page.url()).pathname.split('/').at(-1)
}

try {
  page = await signIn('owner')
  const [vehicle] = await api(page, '/user-vehicles')
  const due = await api(page, `/user-vehicles/${vehicle.userVehicleId}/maintenance-status`)
  assert.equal(due.dueStatus, 'OVERDUE')
  const initial = await api(page, '/notification-settings')
  assert.equal(initial.emailTransport, 'mock', 'Refuse real email mode')
  assert.equal(initial.emailVerified, true)
  assert.equal(initial.remindersEnabled, false)
  await api(page, '/demo/reminders/run', 'POST')
  assert.equal((await api(page, '/demo/email-outbox')).items.length, 0)
  passed('Firebase verified identity, active vehicle, and no email before opt-in')

  await page.goto(`${base}/notifications/settings`)
  await page.getByRole('switch', { name: 'Bật nhắc bảo dưỡng' }).click()
  await page.locator('#channel-EMAIL label').click()
  assert.equal(await page.getByRole('checkbox', { name: 'Email', exact: true }).isChecked(), true)
  await page.getByRole('spinbutton', { name: 'Nhắc trước hạn' }).fill('7')
  const saveResponse = page.waitForResponse(r => r.url().endsWith('/notification-settings') && r.request().method() === 'PUT')
  await page.getByRole('button', { name: 'Lưu', exact: true }).click()
  assert.equal((await saveResponse).status(), 200)
  await page.getByRole('button', { name: 'Lưu', exact: true }).waitFor({ state: 'visible' })
  const saved = await api(page, '/notification-settings')
  assert.equal(saved.remindersEnabled, true)
  assert.equal(saved.reminderLeadDays, 7)
  assert.equal(saved.channels.find(c => c.channel === 'EMAIL').enabled, true)
  await screenshot('settings')
  passed('Save reminder and Email preferences through UI')

  await page.getByRole('link', { name: 'Mở hộp thư demo', exact: true }).click()
  await scan()
  let outbox = await api(page, '/demo/email-outbox')
  assert.equal(outbox.items.length, 1)
  const email = outbox.items[0]
  assert.equal(email.deliveryState, 'mock')
  assert.ok(email.payload.body.includes('38,210'))
  assert.ok(!email.payload.body.includes('51A-11111'))
  assert.ok(!email.payload.body.includes('VF6ECO20240000001'))
  await page.getByRole('heading', { name: email.payload.subject, exact: true }).waitFor()
  await page.frameLocator('iframe').getByRole('heading', { name: 'EV Care', exact: true }).waitFor()
  await screenshot('outbox-desktop')
  await scan()
  await scan()
  outbox = await api(page, '/demo/email-outbox')
  assert.equal(outbox.items.length, 1)
  assert.equal(outbox.items[0].attempts, 1)
  passed('Generate one mock email, render HTML, and prevent duplicate dispatch')

  await page.setViewportSize({ width: 390, height: 844 })
  await screenshot('outbox-mobile')
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'No page overflow on mobile')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('link', { name: 'Xem lời nhắc và hành động', exact: true }).click()
  await page.getByRole('heading', { name: 'Lời nhắc bảo dưỡng', exact: true }).waitFor()
  const reminder = await api(page, `/notifications/reminders/${email.reminderId}`)
  assert.equal(reminder.userVehicleId, vehicle.userVehicleId)
  assert.equal(reminder.details.reason, 'BOTH')
  await screenshot('reminder-detail')
  passed('Reminder context and mobile email preview')

  const other = await signIn('other')
  await api(other, `/notifications/reminders/${email.reminderId}`, 'GET', undefined, 404)
  assert.equal((await api(other, '/demo/email-outbox')).items.length, 0)
  passed('Deny another owner access to reminder and email')

  await page.getByRole('link', { name: 'Hỏi trợ lý', exact: true }).click()
  await page.waitForURL('**/ai/new?**')
  assert.equal(new URL(page.url()).searchParams.get('userVehicleId'), vehicle.userVehicleId)
  await page.getByRole('textbox', { name: 'Nhập câu hỏi' }).waitFor()
  assert.ok((await page.getByRole('textbox', { name: 'Nhập câu hỏi' }).inputValue()).includes(email.reminderId))
  passed('Open assistant with correct vehicle and prefilled reminder question')
  if (useLlm) {
    await ask(`Hãy giải thích lời nhắc bảo dưỡng ${email.reminderId} của tôi. Vì sao xe bị nhắc theo cả số km và thời gian? Dữ liệu lúc nhắc khác gì tình trạng hiện tại? Hãy trích nguyên dấu thời gian ghi nhận dữ liệu lời nhắc, bao gồm múi giờ.`, 'get_reminder_context')
    assert.ok(llmTurns.at(-1).answer.includes(reminder.details.capturedAt), 'Preserve exact snapshot timestamp and timezone in the answer')
    await ask('Đổi thời gian nhắc trước thành 10 ngày cho tôi; giữ nguyên bật nhắc bảo dưỡng và nhận Email.', 'update_reminder_settings')
    assert.equal((await api(page, '/notification-settings')).reminderLeadDays, 10)
    await ask('Tắt riêng email nhắc bảo dưỡng cho tôi, vẫn giữ bật nhắc bảo dưỡng trong ứng dụng.', 'update_reminder_settings')
    let settings = await api(page, '/notification-settings')
    assert.equal(settings.channels.find(c => c.channel === 'EMAIL').enabled, false)
    assert.equal(settings.remindersEnabled, true)
    await screenshot('agent-settings')
    await page.goto(`${base}/notifications/settings`)
    await page.reload()
    assert.equal(await page.getByRole('checkbox', { name: 'Email', exact: true }).isChecked(), false)
    assert.equal(await page.getByRole('spinbutton', { name: 'Nhắc trước hạn' }).inputValue(), '10')
    await page.goto(`${base}/ai/new?userVehicleId=${vehicle.userVehicleId}`)
    await ask('Bật nhắc bảo dưỡng qua Email cho tôi và nhắc trước 7 ngày.', 'update_reminder_settings')
    settings = await api(page, '/notification-settings')
    assert.equal(settings.channels.find(c => c.channel === 'EMAIL').enabled, true)
    assert.equal(settings.reminderLeadDays, 7)
    await ask('Cài đặt nhắc bảo dưỡng hiện tại của tôi như thế nào? Email có bật không, nhắc trước mấy ngày và áp dụng cho xe nào?', 'get_reminder_settings')
    assert.equal((await api(page, '/notification-settings')).reminderLeadDays, 7)
    passed('Real LLM explains reminder and persists settings through shared tools')
  }

  const cancelledBookingId = await bookFromReminder(email.reminderId, vehicle.userVehicleId, due.nextMilestone.odoMilestoneKm)
  await screenshot('booking-ticket')
  await api(page, '/demo/reminders/run', 'POST')
  const paused = await api(page, `/notifications/reminders/${email.reminderId}`)
  assert.equal(paused.resolutionReason, 'HAS_BOOKING')
  assert.equal(paused.hasCurrentBooking, true)
  assert.equal((await api(page, '/demo/email-outbox')).items.length, 1)
  await page.goto(`${base}/notifications/reminders/${email.reminderId}`)
  await page.getByRole('link', { name: 'Xem lịch hẹn', exact: true }).waitFor()
  assert.equal(await page.getByRole('link', { name: 'Đặt lịch theo mốc hiện tại', exact: true }).count(), 0)
  await screenshot('reminder-paused')
  passed('Book through UI for correct vehicle/milestone and pause reminder')

  // The demo exposes cancellation in the workshop portal, not the owner ticket.
  const shop = await signIn('workshop', 'workshop')
  await shop.goto(`${base}/technician/board/${cancelledBookingId}`)
  await shop.getByRole('dialog').getByRole('button', { name: 'Huỷ lịch', exact: true }).click()
  const cancellation = shop.getByRole('alertdialog', { name: 'Huỷ lịch hẹn', exact: true })
  await cancellation.locator('input[value="OTHER"]').check()
  await cancellation.getByLabel('Ghi chú', { exact: false }).fill('Kiểm thử mở lại lời nhắc sau hủy lịch')
  const cancelResponse = shop.waitForResponse(r => r.url().endsWith(`/bookings/${cancelledBookingId}/transitions`) && r.request().method() === 'POST')
  await cancellation.getByRole('button', { name: 'Huỷ lịch', exact: true }).click()
  assert.equal((await cancelResponse).status(), 200)
  assert.equal((await api(page, `/bookings/${cancelledBookingId}`)).status, 'cancelled')
  await api(page, '/demo/reminders/run', 'POST')
  const reopened = await api(page, `/notifications/reminders/${email.reminderId}`)
  assert.equal(reopened.resolved, false)
  assert.equal(reopened.hasCurrentBooking, false)
  assert.equal((await api(page, '/demo/email-outbox')).items.length, 1)
  await page.goto(`${base}/notifications/reminders/${email.reminderId}`)
  await page.getByRole('link', { name: 'Đặt lịch theo mốc hiện tại', exact: true }).waitFor()
  await screenshot('reminder-reopened')
  passed('Cancel through UI, reopen reminder, and retain one original email')

  const completedBookingId = await bookFromReminder(email.reminderId, vehicle.userVehicleId, due.nextMilestone.odoMilestoneKm)
  const board = await api(shop, '/workshop-owner/bookings')
  const booked = await api(page, `/bookings/${completedBookingId}`)
  assert.equal(booked.bookingDate, board.demoNow.slice(0, 10), 'Completion test requires a booking for the demo clock date')
  await shop.goto(`${base}/technician/board/${completedBookingId}`)
  const detail = shop.getByRole('dialog')
  await detail.getByRole('button', { name: 'Check-in', exact: true }).click()
  await detail.getByRole('button', { name: 'Bắt đầu làm', exact: true }).click()
  await detail.getByRole('button', { name: 'Hoàn tất', exact: true }).click()
  const completion = shop.getByRole('dialog', { name: /Hoàn tất dịch vụ/ })
  await completion.getByLabel(/Chi phí thực tế/).fill('350000')
  await completion.getByRole('button', { name: 'Hoàn tất', exact: true }).click()
  await shop.getByText('350.000 ₫', { exact: true }).waitFor()
  await shop.screenshot({ path: path.join(artifacts, 'workshop-completed.png'), fullPage: true, animations: 'disabled' })
  const completed = await api(page, `/bookings/${completedBookingId}`)
  assert.equal(completed.status, 'completed')
  assert.equal(completed.actualCost, 350000)
  await api(page, '/demo/reminders/run', 'POST')
  const closed = await api(page, `/notifications/reminders/${email.reminderId}`)
  assert.equal(closed.resolved, true)
  assert.equal(closed.resolutionReason, 'MAINTENANCE_COMPLETED')
  assert.equal(closed.odoMilestoneKm, due.nextMilestone.odoMilestoneKm, 'Keep original reminder snapshot')
  assert.equal(closed.currentStatus.nextMilestone.odoMilestoneKm, 48000)
  assert.equal(closed.currentStatus.dueStatus, 'NORMAL')
  assert.equal((await api(page, '/demo/email-outbox')).items.length, 1)
  const records = await api(page, `/user-vehicles/${vehicle.userVehicleId}/service-records`)
  assert.equal(records.items.filter(record => record.bookingId === completedBookingId && record.source === 'EV_CARE').length, 1)
  await page.goto(`${base}/notifications/reminders/${email.reminderId}`)
  await page.getByText('Đã hoàn tất bảo dưỡng; mốc tiếp theo được tính lại.', { exact: true }).waitFor()
  const nextBooking = new URL(await page.getByRole('link', { name: 'Đặt lịch theo mốc hiện tại', exact: true }).getAttribute('href'), base)
  assert.equal(nextBooking.searchParams.get('userVehicleId'), vehicle.userVehicleId)
  assert.equal(nextBooking.searchParams.get('odoMilestone'), '48000')
  await screenshot('reminder-completed')
  await page.goto(`${base}/bookings/${completedBookingId}`)
  await page.getByText(/350\.000 ₫/).waitFor()
  await screenshot('completed-ticket')
  passed('Workshop completes maintenance, closes old reminder, advances milestone, and preserves email snapshot')

  await page.goto(`${base}/notifications/settings`)
  await page.getByRole('checkbox', { name: 'Email', exact: true }).waitFor()
  await page.locator('#channel-EMAIL label').click()
  const optOutResponse = page.waitForResponse(r => r.url().endsWith('/notification-settings') && r.request().method() === 'PUT')
  await page.getByRole('button', { name: 'Lưu', exact: true }).click()
  assert.equal((await optOutResponse).status(), 200)
  await page.reload()
  assert.equal(await page.getByRole('checkbox', { name: 'Email', exact: true }).isChecked(), false)
  assert.equal((await api(page, '/notification-settings')).remindersEnabled, true)
  await api(page, '/demo/reminders/run', 'POST')
  assert.equal((await api(page, '/demo/email-outbox')).items.length, 1)
  await screenshot('email-opted-out')
  passed('Opt out Email through UI and retain setting after reload')

  assert.deepEqual(browserErrors, [])
} catch (error) {
  failure = { name: error.name, message: error.message }
  console.error(`${error.name}: ${error.message}`)
  if (page && !page.isClosed()) await screenshot('failure').catch(() => {})
  process.exitCode = 1
} finally {
  const cleanup = []
  for (const identity of testUsers) {
    try {
      await identity.tab.evaluate(async expected => {
        const { getFirebaseAuth } = await import('/src/features/auth/firebase.ts')
        const { deleteUser } = await import('/node_modules/.vite/deps/firebase_auth.js')
        const auth = getFirebaseAuth()
        if (!auth?.emulatorConfig || auth.currentUser?.uid !== expected.uid || auth.currentUser?.email !== expected.email) {
          throw new Error('Refuse to delete an identity outside this test')
        }
        await deleteUser(auth.currentUser)
      }, { uid: identity.uid, email: identity.email })
      cleanup.push({ identity: identity.email, removed: true })
    } catch (error) {
      cleanup.push({ identity: identity.email, removed: false, error: error.name })
    }
  }
  await Promise.all(contexts.map(context => context.close()))
  await browser.close()
  await writeFile(path.join(artifacts, 'results.json'), JSON.stringify({
    mode: 'mock', realLlm: useLlm, base, demoNow, results, llmTurns, browserErrors, failure, cleanup,
  }, null, 2))
  console.log(`Artifacts: ${artifacts}`)
}
