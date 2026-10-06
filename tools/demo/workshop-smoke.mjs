// Two browser contexts, real Firebase Emulator popup + HTTP + configured LLM.
// Backend must use DEMO_NOW=today at 09:00+07:00 to demo today's full service loop.
import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { completeRegistration } from './registration-fixture.mjs'

const base = process.env.DEMO_FRONTEND_URL || 'http://127.0.0.1:5173'
await mkdir('artifacts', { recursive: true })
const browser = await chromium.launch({ channel: process.env.DEMO_BROWSER_CHANNEL || 'chrome', headless: true })
const driverContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const workshopContext = await browser.newContext({ viewport: { width: 1440, height: 1000 }, recordVideo: { dir: 'artifacts', size: { width: 1280, height: 720 } } })
const owner = await driverContext.newPage()
const shop = await workshopContext.newPage()
const failures = []
for (const page of [owner, shop]) page.on('pageerror', e => failures.push(e.message))
async function signIn(page, uid, email) {
  await page.evaluate(async ({ uid, email }) => {
    const { getFirebaseAuth } = await import('/src/features/auth/firebase.ts')
    const { GoogleAuthProvider, signInWithCredential } = await import('/node_modules/.vite/deps/firebase_auth.js')
    await signInWithCredential(getFirebaseAuth(), GoogleAuthProvider.credential(JSON.stringify({ sub: uid, email, email_verified: true, name: uid })))
  }, { uid, email })
}
async function api(page, path, method = 'GET', body) {
  return page.evaluate(async ({ path, method, body }) => {
    const { getIdToken } = await import('/src/features/auth/firebase.ts')
    const response = await fetch(`/api/v1${path}`, { method, headers: { Authorization: `Bearer ${await getIdToken()}`, ...(body ? { 'Content-Type': 'application/json' } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
    if (!response.ok) throw new Error(`HTTP ${response.status} at ${path}`)
    return response.json()
  }, { path, method, body })
}
const result = {}
let loginPopup
try {
  // Seed fictional Google account into emulator so the real popup can select it.
  const seedContext = await browser.newContext()
  const seed = await seedContext.newPage()
  await seed.goto(base)
  await signIn(seed, 'workshop-browser-1', 'workshop1@example.com')
  await seed.waitForURL(url => ['/dashboard', '/onboarding/profile', '/onboarding/vehicle'].includes(url.pathname), { timeout: 30000 })
  await completeRegistration(seed)
  await seedContext.close()

  await shop.goto(`${base}/workshop/login`)
  const popupPromise = shop.waitForEvent('popup')
  await shop.getByRole('button', { name: /Google/ }).click()
  const popup = await popupPromise
  loginPopup = popup
  popup.on('pageerror', e => failures.push(e.message))
  await popup.waitForLoadState('load')
  await popup.getByText('workshop1@example.com', { exact: true }).first().waitFor()
  // Emulator sends one postMessage; wait for Firebase's relay iframe to attach.
  await shop.waitForFunction(() => [...document.querySelectorAll('iframe')].some(f => f.src.includes('/emulator/auth/iframe')))
  await popup.waitForTimeout(1000)
  await popup.locator('.js-reuse-account', { hasText: 'workshop1@example.com' }).first().click()
  await shop.waitForURL(url => url.pathname === '/technician' || url.pathname.startsWith('/workshop/onboarding/'), { timeout: 30000 })
  await completeRegistration(shop, 'workshop')
  await shop.goto(`${base}/technician`)
  await shop.getByRole('heading', { name: /Xin chào/ }).waitFor()
  await shop.reload()
  await shop.getByRole('heading', { name: /Xin chào/ }).waitFor()
  const { data: board } = await api(shop, '/workshop-owner/bookings')
  const day = board.demoNow.slice(0, 10)
  if (Number(board.demoNow.slice(11, 13)) >= 14) throw new Error('Set DEMO_NOW before 14:00 for this full-service test')
  result.workshopPopupLogin = true
  result.workshopSessionReload = true

  await owner.goto(base)
  await signIn(owner, 'workshop-demo-driver', 'workshop-driver@example.com')
  await owner.waitForURL(url => ['/dashboard', '/onboarding/profile', '/onboarding/vehicle'].includes(url.pathname), { timeout: 30000 })
  await completeRegistration(owner)
  await owner.goto(`${base}/dashboard`)
  await owner.getByRole('heading', { name: /Xin chào/ }).waitFor()
  await api(owner, '/demo/reset', 'POST')
  const { data: [vehicle] } = await api(owner, '/user-vehicles')
  const { data: conversation } = await api(owner, '/conversations', 'POST', { userVehicleId: vehicle.userVehicleId })
  await owner.goto(`${base}/ai/${conversation.id}`)
  await owner.getByRole('textbox', { name: 'Nhập câu hỏi' }).fill(`Trong demo, hãy tra slot và tạo đề xuất đặt lịch tại xưởng ${board.workshopId}, ngày ${day}, lúc 14:00 cho xe hiện tại. Ngày backend demo là ${day}, 09:00 sáng, nên 14:00 còn trong tương lai. Tôi sẽ xác nhận trên giao diện. Dùng propose_booking.`)
  const responsePromise = owner.waitForResponse(r => r.url().includes('/messages') && r.request().method() === 'POST')
  await owner.getByRole('button', { name: 'Gửi', exact: true }).click()
  const stream = await (await responsePromise).text()
  if (!stream.includes('event: message.completed') || !stream.includes('propose_booking')) throw new Error('LLM did not produce booking proposal')
  await owner.getByRole('button', { name: 'Xác nhận đặt lịch', exact: true }).click({ timeout: 120000 })
  await owner.waitForURL('**/booking/confirm?**')
  await owner.getByRole('button', { name: 'Xác nhận', exact: true }).click()
  await owner.waitForURL('**/bookings/**')
  const bid = new URL(owner.url()).pathname.split('/').at(-1)
  const { data: ticket } = await api(owner, `/bookings/${bid}`)
  result.realLlmBooking = true

  await shop.reload()
  const appointment = shop.locator(`a[href="/technician/board/${bid}"]`)
  await appointment.waitFor()
  await shop.screenshot({ path: 'artifacts/workshop-restored-dashboard.png', fullPage: true })
  await appointment.click()
  await shop.waitForURL(`**/technician/board/${bid}`)
  const detail = shop.getByRole('dialog')
  await detail.getByRole('button', { name: 'Check-in', exact: true }).click()
  await detail.getByRole('button', { name: 'Bắt đầu làm', exact: true }).click()
  await detail.getByRole('button', { name: 'Hoàn tất', exact: true }).click()
  const completion = shop.getByRole('dialog', { name: /Hoàn tất dịch vụ/ })
  await completion.getByLabel(/Chi phí thực tế/).fill('350000')
  await completion.getByRole('button', { name: 'Hoàn tất', exact: true }).click()
  await shop.getByText('350.000 ₫', { exact: true }).waitFor()
  await shop.reload()
  await shop.getByText('350.000 ₫', { exact: true }).waitFor()
  await shop.screenshot({ path: 'artifacts/workshop-completed.png', fullPage: true })

  await owner.reload()
  await owner.getByText(/350\.000 ₫/).waitFor()
  const { data: finalTicket } = await api(owner, `/bookings/${bid}`)
  if (finalTicket.status !== 'completed' || finalTicket.actualCost !== 350000 || finalTicket.history.length !== 4) throw new Error('Owner ticket differs from workshop result')
  await owner.screenshot({ path: 'artifacts/owner-workshop-result.png', fullPage: true })
  await owner.goto(`${base}/ai/${conversation.id}`)
  await owner.getByText(`Xưởng cập nhật lịch ${ticket.bookingCode}: COMPLETED.`, { exact: true }).waitFor()
  result.sharedBookingId = bid
  result.serviceLoop = ['CONFIRMED', 'CHECKED_IN', 'IN_PROGRESS', 'COMPLETED']
  result.ownerTicketAndChatUpdated = true
  result.actualCost = finalTicket.actualCost
  await owner.goto(`${base}/c/${ticket.bookingCode}`)
  await owner.waitForURL(`**/bookings/${bid}`)
  await owner.getByText(/350\.000 ₫/).waitFor()
  const { data: past } = await api(owner, '/bookings?scope=PAST')
  const { data: records } = await api(owner, `/user-vehicles/${vehicle.userVehicleId}/service-records`)
  if (!past.items.some(item => item.bookingId === bid && item.status === 'COMPLETED') || !records.items.some(item => item.bookingId === bid && item.actualCost === 350000)) throw new Error('Completed booking missing from shared history')
  result.qrAndCompletedHistory = true
  await shop.goto(`${base}/technician/notifications`)
  await shop.getByRole('heading', { name: 'Thông báo', exact: true }).waitFor()
  await shop.screenshot({ path: 'artifacts/workshop-restored-notifications.png', fullPage: true })
  result.originalLayoutsRestored = true
  if (failures.length) throw new Error(failures.join('; '))
  console.log('Workshop popup login, reload, real LLM booking, service completion, owner ticket/chat: PASS')
} catch (error) {
  if (loginPopup && !loginPopup.isClosed()) {
    console.error('Popup:', (await loginPopup.locator('body').innerText()).slice(0, 1800))
    await loginPopup.screenshot({ path: 'artifacts/workshop-popup-failure.png' })
  }
  await shop.screenshot({ path: 'artifacts/workshop-failure.png', fullPage: true })
  await owner.screenshot({ path: 'artifacts/owner-workshop-failure.png', fullPage: true })
  console.error(error.message)
  process.exitCode = 1
} finally {
  await driverContext.close()
  await workshopContext.close()
  await browser.close()
  await writeFile('artifacts/workshop-results.json', JSON.stringify({ result, browserErrors: failures }, null, 2))
}
