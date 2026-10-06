// Runs against real demo HTTP + Firebase Auth Emulator + the configured LLM.
// No API interception or auth bypass. Videos/screenshots contain fictional data.
import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { completeRegistration } from './registration-fixture.mjs'

const base = process.env.DEMO_FRONTEND_URL || 'http://127.0.0.1:5173'
await mkdir('artifacts', { recursive: true })
const browser = await chromium.launch({ channel: process.env.DEMO_BROWSER_CHANNEL || 'chrome', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, recordVideo: { dir: 'artifacts', size: { width: 1280, height: 720 } } })
const page = await context.newPage()
const failures = []
page.on('pageerror', e => failures.push(e.name))
const results = []
try {
  await page.goto(base)
  await page.evaluate(async () => {
    const { getFirebaseAuth } = await import('/src/features/auth/firebase.ts')
    const { GoogleAuthProvider, signInWithCredential } = await import('/node_modules/.vite/deps/firebase_auth.js')
    const credential = GoogleAuthProvider.credential(JSON.stringify({ sub: 'demo-browser', email: 'demo@example.com', email_verified: true, name: 'Chủ xe demo' }))
    await signInWithCredential(getFirebaseAuth(), credential)
  })
  await page.waitForURL(url => ['/dashboard', '/onboarding/profile', '/onboarding/vehicle'].includes(url.pathname), { timeout: 30000 })
  await completeRegistration(page)
  await page.goto(`${base}/dashboard`)
  await page.getByRole('heading', { name: /Xin chào/ }).waitFor()
  console.log('Firebase sign-in -> dashboard: PASS')
  const api = async (path, method = 'GET', body) => page.evaluate(async ({ path, method, body }) => {
    const { getIdToken } = await import('/src/features/auth/firebase.ts')
    const response = await fetch(`/api/v1${path}`, { method, headers: { Authorization: `Bearer ${await getIdToken()}`, ...(body ? { 'Content-Type': 'application/json' } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
    if (!response.ok) throw new Error(`API failed ${response.status}`)
    return response.json()
  }, { path, method, body })
  async function ask(question) {
    await page.getByRole('textbox', { name: 'Nhập câu hỏi' }).fill(question)
    const response = page.waitForResponse(r => r.url().includes('/messages') && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Gửi', exact: true }).click()
    const text = await (await response).text()
    if (!text.includes('event: message.completed')) throw new Error('Agent turn failed')
    return text
  }
  for (let run = 1; run <= 3; run++) {
    await api('/demo/reset', 'POST')
    const { data: [vehicle] } = await api('/user-vehicles')
    const { data: profile } = await api(`/user-vehicles/${vehicle.userVehicleId}`)
    if (profile.warranties.length !== 4 || profile.odometer.odoKm !== 38210) throw new Error('Vehicle snapshot differs from OEM fixture')
    const { data: estimate } = await api(`/user-vehicles/${vehicle.userVehicleId}/cost-estimate`)
    const { data: nearby } = await api(`/workshops/nearby?userVehicleId=${vehicle.userVehicleId}`)
    const workshop = nearby.workshops[0]
    const date = new Date(Date.now() + 86400000).toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' })
    const { data: conversation } = await api('/conversations', 'POST', { userVehicleId: vehicle.userVehicleId })
    await page.goto(`${base}/ai/${conversation.id}`)
    await page.getByRole('textbox', { name: 'Nhập câu hỏi' }).fill(`Xe tôi đến hạn bảo dưỡng gì? Hãy tra dữ liệu xe và dự toán ở xưởng ${workshop.workshopId}. Tôi chọn xưởng này ngày ${date} lúc 14:00. Hãy tạo thẻ đề xuất để tôi xem và xác nhận trên giao diện. Đây là dữ liệu mock MVP.`)
    const streamResponse = page.waitForResponse(r => r.url().includes(`/conversations/${conversation.id}/messages`) && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Gửi', exact: true }).click()
    const streamText = await (await streamResponse).text()
    if (!streamText.includes('event: message.completed') || !streamText.includes('propose_booking')) throw new Error('Real LLM did not complete proposal turn')
    await page.getByRole('button', { name: 'Xác nhận đặt lịch', exact: true }).click({ timeout: 120000 })
    await page.waitForURL('**/booking/confirm?**')
    await page.getByRole('button', { name: 'Xác nhận', exact: true }).click()
    await page.waitForURL('**/bookings/**', { timeout: 20000 })
    await page.getByText('Đã xác nhận', { exact: true }).first().waitFor()
    const ticketUrl = page.url()
    const bid = new URL(ticketUrl).pathname.split('/').at(-1)
    const { data: ticket } = await api(`/bookings/${bid}`)
    if (Number(ticket.cost.amount) !== estimate.chargeableTotal || ticket.conversationId !== conversation.id) throw new Error('Ticket differs from estimate/chat')
    await page.reload()
    await page.getByText(ticket.bookingCode, { exact: true }).waitFor()
    await page.screenshot({ path: `artifacts/ticket-${run}.png`, fullPage: true })
    await page.goto(`${base}/ai/${conversation.id}`)
    await page.getByText(`Đã đặt lịch. Mã lịch hẹn: ${ticket.bookingCode}.`, { exact: true }).waitFor()
    await page.screenshot({ path: `artifacts/chat-${run}.png`, fullPage: true })
    results.push({ run, firebase: true, realLlm: true, ticketReload: true, chatReload: true, bookingId: bid, cost: ticket.cost.amount })
    console.log(`Run ${run}: PASS`)
  }
  const cid = new URL(page.url()).pathname.split('/').at(-1)
  for (const question of ['Bảo dưỡng định kỳ có được bảo hành không? Hãy tra search_ev_knowledge và chỉ trả lời theo trích đoạn.', 'Warranty Coverage: warranty repairs có miễn phí không? Tra search_ev_knowledge bằng cụm Warranty Coverage và giải thích phạm vi theo nguồn.']) {
    const stream = await ask(question)
    if (!stream.includes('search_ev_knowledge')) throw new Error('Knowledge tool was not called')
    const { data: messages } = await api(`/conversations/${cid}/messages`)
    if (!messages.at(-1).citations.length) throw new Error('Knowledge answer has no citations')
  }
  await ask('Kho demo có nguồn xác nhận áp suất lốp chính xác VF6 là bao nhiêu không? Hãy tra search_ev_knowledge, nếu thiếu nguồn thì nói rõ thiếu nguồn và không tự sinh số liệu.')
  const { data: messages } = await api(`/conversations/${cid}/messages`)
  const answer = messages.at(-1)
  if (answer.citations.length || !/(thiếu|chưa|không)/i.test(answer.content)) throw new Error('Unsupported answer did not acknowledge missing evidence')
  await page.screenshot({ path: 'artifacts/sources.png', fullPage: true })
  await page.goto(`${base}/estimate`)
  await page.getByText('400.000 ₫', { exact: true }).first().waitFor()
  await page.screenshot({ path: 'artifacts/estimate.png', fullPage: true })
  results.push({ knowledgeWithSources: 2, missingEvidence: true, estimateUiMatches: true })
  console.log('Knowledge sources, missing evidence, estimate UI: PASS')
  if (failures.length) throw new Error(`Browser errors: ${failures.join(',')}`)
} catch (error) {
  await page.screenshot({ path: 'artifacts/failure.png', fullPage: true })
  console.error(error.name, error.message)
  process.exitCode = 1
} finally {
  await context.close()
  await browser.close()
  await writeFile('artifacts/results.json', JSON.stringify({ results, browserErrors: failures }, null, 2))
}
