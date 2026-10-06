// Records the MVP demo video: real browser, demo HTTP backend, Firebase Auth Emulator
// and the configured real LLM. No API interception; captions are a visual overlay only.
// Backend must run with DEMO_NOW=today 09:00+07:00 so a 14:00 slot is bookable today.
import { chromium } from '@playwright/test'
import { spawnSync } from 'node:child_process'
import { mkdir, readdir, rm, writeFile } from 'node:fs/promises'
import { completeRegistration } from './registration-fixture.mjs'

const base = process.env.DEMO_FRONTEND_URL || 'http://127.0.0.1:5173'
const out = 'artifacts/video'
const size = { width: 1280, height: 800 }
const OWNER = { uid: 'video-owner', email: 'chuxe.video@example.com', name: 'Nguyễn Minh Anh' }
const SHOP = { uid: 'video-workshop-1', email: 'workshop1@example.com', name: 'Xưởng demo EV Care 1' }
const ACTUAL_COST = '380000'

await rm(out, { recursive: true, force: true })
await mkdir(out, { recursive: true })
const browser = await chromium.launch({ channel: process.env.DEMO_BROWSER_CHANNEL || 'chrome', headless: true })
const failures = []
const timeline = []
const started = Date.now()
const mark = label => timeline.push({ at: ((Date.now() - started) / 1000).toFixed(1), label })
const pause = (page, ms) => page.waitForTimeout(ms)

function captions(context) {
  return context.addInitScript(() => {
    const paint = () => {
      let raw = null
      try { raw = localStorage.getItem('__demoCaption') } catch { return }
      let el = document.getElementById('__demo_caption')
      if (!raw) return el?.remove()
      if (!el) {
        el = document.createElement('div')
        el.id = '__demo_caption'
        el.style.cssText = 'position:fixed;left:50%;top:12px;transform:translateX(-50%);z-index:2147483647;pointer-events:none;max-width:84%;display:flex;gap:12px;align-items:center;padding:12px 20px;border-radius:14px;background:rgba(17,24,32,.92);color:#EEF2F5;font:600 18px/1.4 "Be Vietnam Pro",system-ui,sans-serif;box-shadow:0 8px 28px rgba(0,0,0,.25)'
        document.documentElement.appendChild(el)
      }
      const { step, text } = JSON.parse(raw)
      el.innerHTML = `<span style="flex:none;padding:3px 10px;border-radius:999px;background:#19C37D;color:#0A0E13;font-weight:800;font-size:14px">${step}</span><span></span>`
      el.lastChild.textContent = text
    }
    window.__paintCaption = paint
    document.addEventListener('DOMContentLoaded', paint)
    if (document.readyState !== 'loading') paint()
  })
}

async function caption(page, step, text) {
  mark(`${step} ${text}`)
  await page.evaluate(({ step, text }) => {
    localStorage.setItem('__demoCaption', JSON.stringify({ step, text }))
    window.__paintCaption?.()
  }, { step, text })
}

async function card(page, title, lines, ms) {
  await page.evaluate(() => { try { localStorage.removeItem('__demoCaption') } catch { /* about:blank */ } })
  await page.setContent(`<!doctype html><html><head><meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;600;800&display=swap" rel="stylesheet">
    <style>body{margin:0;height:100vh;display:grid;place-items:center;background:#111820;color:#EEF2F5;font-family:"Be Vietnam Pro",system-ui,sans-serif}
    main{max-width:900px;padding:0 48px}.bolt{color:#19C37D;font-weight:800;letter-spacing:.08em;font-size:15px;text-transform:uppercase}
    h1{font-size:46px;font-weight:800;letter-spacing:-.025em;margin:14px 0 22px;line-height:1.15}
    li{font-size:21px;color:#C9D1D9;margin:10px 0;line-height:1.45}ul{padding-left:24px;margin:0}</style></head>
    <body><main><div class="bolt">⚡ EV Care · MVP Demo</div><h1>${title}</h1><ul>${lines.map(l => `<li>${l}</li>`).join('')}</ul></main></body></html>`)
  await page.waitForLoadState('networkidle').catch(() => {})
  await pause(page, ms)
}

async function signIn(page, { uid, email, name }) {
  await page.evaluate(async ({ uid, email, name }) => {
    const { getFirebaseAuth } = await import('/src/features/auth/firebase.ts')
    const { GoogleAuthProvider, signInWithCredential } = await import('/node_modules/.vite/deps/firebase_auth.js')
    await signInWithCredential(getFirebaseAuth(), GoogleAuthProvider.credential(JSON.stringify({ sub: uid, email, email_verified: true, name })))
  }, { uid, email, name })
}

async function api(page, path, method = 'GET', body) {
  return page.evaluate(async ({ path, method, body }) => {
    const { getIdToken } = await import('/src/features/auth/firebase.ts')
    const response = await fetch(`/api/v1${path}`, { method, headers: { Authorization: `Bearer ${await getIdToken()}`, ...(body ? { 'Content-Type': 'application/json' } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
    if (!response.ok) throw new Error(`HTTP ${response.status} at ${path}`)
    return response.json()
  }, { path, method, body })
}

/** Real Firebase Emulator account picker; the account must already exist in the emulator. */
async function popupLogin(page, email) {
  const popupPromise = page.waitForEvent('popup')
  await page.getByRole('button', { name: /Google/ }).first().click()
  const popup = await popupPromise
  await popup.waitForLoadState('load')
  await page.waitForFunction(() => [...document.querySelectorAll('iframe')].some(f => f.src.includes('/emulator/auth/iframe')))
  await popup.waitForTimeout(1000)
  await popup.locator('.js-reuse-account', { hasText: email }).first().click()
}

async function recorded(options = {}) {
  const context = await browser.newContext({ viewport: size, recordVideo: { dir: out, size }, ...options })
  await captions(context)
  const page = await context.newPage()
  page.on('pageerror', e => failures.push(e.message))
  return { context, page, t0: Date.now(), cuts: [] }
}

/** Runs a technical wait (login, page boot) and marks everything past `keep` seconds for trimming. */
async function trimmed(seg, keep, action) {
  const start = Date.now()
  await action()
  const at = ms => (ms - seg.t0) / 1000
  if ((Date.now() - start) / 1000 > keep + 0.5) seg.cuts.push([at(start) + keep / 2, at(Date.now()) - keep / 2])
}

const segments = []
async function finish(seg, name) {
  await seg.context.close()
  await seg.page.video().saveAs(`${out}/${name}.webm`)
  await seg.page.video().delete()
  segments.push({ name, cuts: seg.cuts })
}

/** Cuts the marked waits, joins the segments and encodes an H.264 MP4. */
function assemble(target) {
  const ffmpeg = process.env.FFMPEG || 'ffmpeg'
  const inputs = segments.flatMap(({ name }) => ['-i', `${out}/${name}.webm`])
  const parts = segments.map(({ cuts }, i) => {
    const keep = cuts.length ? `select='not(${cuts.map(([a, b]) => `between(t,${a.toFixed(2)},${b.toFixed(2)})`).join('+')})',` : ''
    return `[${i}:v]${keep}setpts=N/FRAME_RATE/TB,fps=25[v${i}]`
  })
  const filter = `${parts.join(';')};${segments.map((_, i) => `[v${i}]`).join('')}concat=n=${segments.length}:v=1:a=0[v]`
  const run = spawnSync(ffmpeg, ['-y', '-v', 'error', ...inputs, '-filter_complex', filter, '-map', '[v]', '-c:v', 'libx264', '-crf', '20', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', target], { stdio: 'inherit' })
  if (run.status !== 0) throw new Error(`ffmpeg failed (set FFMPEG to the ffmpeg binary): ${run.error?.message ?? run.status}`)
}

/** Sends one chat turn through the UI and returns the raw SSE body. */
async function ask(page, question, onSent) {
  const box = page.getByRole('textbox', { name: 'Nhập câu hỏi' })
  await box.click()
  await box.pressSequentially(question, { delay: 18 })
  await pause(page, 500)
  const response = page.waitForResponse(r => r.url().includes('/messages') && r.request().method() === 'POST', { timeout: 150000 })
  await page.getByRole('button', { name: 'Gửi', exact: true }).click()
  await onSent?.()
  const text = await (await response).text()
  if (!text.includes('event: message.completed')) throw new Error(`Agent turn failed: ${text.slice(-300)}`)
  return text
}

const result = {}
try {
  // --- Arrange (not recorded): accounts exist in the emulator and finished registration.
  const seedContext = await browser.newContext()
  const seed = await seedContext.newPage()
  await seed.goto(base)
  await signIn(seed, SHOP)
  await seed.waitForURL(url => ['/dashboard', '/onboarding/profile', '/onboarding/vehicle'].includes(url.pathname), { timeout: 30000 })
  await completeRegistration(seed)
  await seed.goto(`${base}/workshop/login`)
  await popupLogin(seed, SHOP.email)
  await seed.waitForURL(url => url.pathname === '/technician' || url.pathname.startsWith('/workshop/onboarding/'), { timeout: 30000 })
  await completeRegistration(seed, 'workshop')
  await seedContext.close()

  const ownerSeedContext = await browser.newContext()
  const ownerSeed = await ownerSeedContext.newPage()
  await ownerSeed.goto(base)
  await signIn(ownerSeed, OWNER)
  await ownerSeed.waitForURL(url => ['/dashboard', '/onboarding/profile', '/onboarding/vehicle'].includes(url.pathname), { timeout: 30000 })
  await completeRegistration(ownerSeed)
  await api(ownerSeed, '/demo/reset', 'POST')
  await ownerSeedContext.close()

  // --- Part 1: vehicle owner asks the agent and books.
  const one = await recorded()
  const owner = one.page
  await card(owner, 'Trợ lý AI chăm sóc xe điện', [
    'Chủ xe VinFast khó biết khi nào đến hạn bảo dưỡng, chi phí bao nhiêu, đặt lịch ở đâu.',
    'EV Care: agent LangGraph + LLM thật (Gemini) tra dữ liệu xe, dự toán, lịch trống và đề xuất đặt lịch.',
    'Demo: chủ xe hỏi → agent xử lý bằng tool → đặt lịch → xưởng hoàn tất dịch vụ.',
  ], 9000)
  await owner.goto(base)
  await caption(owner, 'Bước 1', 'Chủ xe đăng nhập bằng Google (Firebase Auth Emulator)')
  await pause(owner, 3000)
  await trimmed(one, 3, async () => {
    await popupLogin(owner, OWNER.email)
    await owner.waitForURL('**/dashboard', { timeout: 30000 })
    await owner.getByRole('heading', { name: /Xin chào/ }).waitFor()
  })
  await caption(owner, 'Bước 1', 'Dashboard: VF6 Eco, ODO 38.210 km, đã quá hạn bảo dưỡng mốc 24.000 km')
  await pause(owner, 8000)
  await owner.goto(`${base}/estimate`)
  await owner.getByText('400.000 ₫', { exact: true }).first().waitFor()
  await caption(owner, 'Bước 1', 'Màn dự toán: chi phí ước tính theo gói bảo dưỡng của xưởng (dữ liệu demo)')
  await pause(owner, 8000)

  const { data: [vehicle] } = await api(owner, '/user-vehicles')
  const { data: estimate } = await api(owner, `/user-vehicles/${vehicle.userVehicleId}/cost-estimate`)
  const { data: conversation } = await api(owner, '/conversations', 'POST', { userVehicleId: vehicle.userVehicleId })
  await owner.goto(`${base}/ai/${conversation.id}`)
  await owner.getByRole('textbox', { name: 'Nhập câu hỏi' }).waitFor()
  await caption(owner, 'Bước 2', 'Input: chủ xe hỏi trợ lý AI bằng tiếng Việt tự nhiên')
  const firstStream = await ask(owner, 'Xe tôi đến hạn bảo dưỡng gì? Tìm xưởng gần tôi và cho biết chi phí ước tính.',
    () => caption(owner, 'Bước 2', 'Xử lý: Gemini gọi tool tra bảo dưỡng và dự toán từ dữ liệu xe (không mock LLM)'))
  result.turn1Tools = [...firstStream.matchAll(/"tool": "(\w+)"/g)].map(m => m[1])
  await caption(owner, 'Bước 2', 'Output: hạng mục đến hạn + chi phí ước tính, lấy từ tool chứ không do LLM tự bịa')
  await pause(owner, 12000)
  const warranty = await ask(owner, 'Chi phí bảo dưỡng định kỳ này có được bảo hành chi trả không? Trích nguồn giúp tôi.',
    () => caption(owner, 'Bước 2', 'RAG: agent tra tài liệu chính sách bảo hành VF6'))
  result.warrantyUsedKnowledge = warranty.includes('search_ev_knowledge')
  await caption(owner, 'Bước 2', 'Trả lời theo tài liệu bảo hành, kèm nguồn trích dẫn để chủ xe kiểm chứng')
  await pause(owner, 11000)

  const today = new Date(Date.now()).toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' })
  await caption(owner, 'Bước 3', 'Chủ xe nhờ agent đặt lịch ở xưởng demo 1, hôm nay 14:00')
  let stream = await ask(owner, 'Đặt lịch giúp tôi ở Xưởng demo EV Care 1, hôm nay lúc 14:00. Tạo thẻ đề xuất để tôi xác nhận.',
    () => caption(owner, 'Bước 3', 'Agent tra lịch trống của xưởng rồi gọi tool propose_booking'))
  const proposal = owner.getByRole('button', { name: 'Xác nhận đặt lịch', exact: true })
  for (let retry = 0; retry < 2 && !stream.includes('propose_booking'); retry++) {
    await caption(owner, 'Bước 3', 'Agent hỏi lại để chốt thông tin, chủ xe trả lời')
    stream = await ask(owner, `Đúng vậy: xưởng demo 1, ngày ${today}, 14:00. Hãy tạo thẻ đề xuất để tôi xác nhận.`)
  }
  if (!stream.includes('propose_booking')) throw new Error('LLM did not call propose_booking')
  await proposal.waitFor({ timeout: 30000 })
  await proposal.scrollIntoViewIfNeeded()
  await caption(owner, 'Bước 3', 'Agent tạo thẻ đề xuất. Thẻ chưa giữ chỗ: chủ xe phải tự xác nhận')
  await pause(owner, 10000)
  await proposal.click()
  await owner.waitForURL('**/booking/confirm?**')
  await caption(owner, 'Bước 3', 'Kiểm tra lại xưởng, giờ hẹn và chi phí ước tính, rồi bấm Xác nhận')
  await pause(owner, 5000)
  await owner.getByRole('button', { name: 'Xác nhận', exact: true }).click()
  await owner.waitForURL('**/bookings/**', { timeout: 20000 })
  await owner.getByText('Đã xác nhận', { exact: true }).first().waitFor()
  const bid = new URL(owner.url()).pathname.split('/').at(-1)
  const { data: ticket } = await api(owner, `/bookings/${bid}`)
  await caption(owner, 'Bước 3', `Đặt lịch thành công. Mã lịch hẹn ${ticket.bookingCode}`)
  await pause(owner, 8000)
  const ownerState = await one.context.storageState({ indexedDB: true })
  await finish(one, '1-owner')
  result.bookingCode = ticket.bookingCode
  result.estimateMatchesTicket = Number(ticket.cost.amount) === estimate.chargeableTotal

  // --- Part 2: workshop owner runs the service.
  const two = await recorded()
  const shop = two.page
  await shop.goto(`${base}/workshop/login`)
  await caption(shop, 'Bước 4', 'Chủ xưởng đăng nhập cổng xưởng')
  await pause(shop, 3000)
  const appointment = shop.locator(`a[href="/technician/board/${bid}"]`).first()
  await trimmed(two, 3, async () => {
    await popupLogin(shop, SHOP.email)
    await shop.waitForURL(url => url.pathname === '/technician', { timeout: 60000 })
    await shop.getByRole('heading', { name: /Xin chào/ }).waitFor()
    await appointment.waitFor()
  })
  await appointment.scrollIntoViewIfNeeded()
  await caption(shop, 'Bước 4', `Lịch ${ticket.bookingCode} do agent đề xuất đã có trên trang của xưởng`)
  await pause(shop, 7000)
  await appointment.click()
  await shop.waitForURL(`**/technician/board/${bid}`)
  const detail = shop.getByRole('dialog')
  await caption(shop, 'Bước 5', 'Xưởng xử lý lịch: Check-in → Bắt đầu làm → Hoàn tất')
  await pause(shop, 4000)
  await detail.getByRole('button', { name: 'Check-in', exact: true }).click()
  await pause(shop, 3500)
  await detail.getByRole('button', { name: 'Bắt đầu làm', exact: true }).click()
  await pause(shop, 3500)
  await detail.getByRole('button', { name: 'Hoàn tất', exact: true }).click()
  const completion = shop.getByRole('dialog', { name: /Hoàn tất dịch vụ/ })
  await caption(shop, 'Bước 5', 'Nhập chi phí thực tế khi hoàn tất')
  await completion.getByLabel(/Chi phí thực tế/).pressSequentially(ACTUAL_COST, { delay: 120 })
  await pause(shop, 2000)
  await completion.getByRole('button', { name: 'Hoàn tất', exact: true }).click()
  await shop.getByText('380.000 ₫', { exact: true }).first().waitFor()
  await caption(shop, 'Bước 5', 'Dịch vụ hoàn tất, chi phí thực tế 380.000 ₫')
  await pause(shop, 5000)
  await finish(two, '2-workshop')

  // --- Part 3: owner sees the result in ticket, chat and history.
  const three = await recorded({ storageState: ownerState })
  const back = three.page
  const actual = back.getByText(/380\.000 ₫/).first()
  await trimmed(three, 1, async () => {
    await back.goto(`${base}/bookings/${bid}`)
    await actual.waitFor({ timeout: 30000 })
  })
  await caption(back, 'Bước 6', 'Chủ xe thấy lịch đã hoàn tất, có tiến độ dịch vụ và chi phí thực tế')
  await pause(back, 4000)
  await actual.evaluate(el => el.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  await pause(back, 5000)
  await trimmed(three, 1, async () => {
    await back.goto(`${base}/ai/${conversation.id}`)
    await back.getByText(`Xưởng cập nhật lịch ${ticket.bookingCode}: COMPLETED.`, { exact: true }).waitFor()
  })
  await caption(back, 'Bước 6', 'Hội thoại với agent cũng tự cập nhật trạng thái từ xưởng')
  await pause(back, 7000)
  await trimmed(three, 1, async () => {
    await back.goto(`${base}/history`)
    await back.getByText(/380\.000/).first().waitFor({ timeout: 15000 })
  })
  await caption(back, 'Bước 6', 'Lịch sử dịch vụ của xe được cập nhật')
  await pause(back, 6000)
  const { data: final } = await api(back, `/bookings/${bid}`)
  result.finalStatus = final.status
  result.actualCost = final.actualCost
  await card(back, 'Luồng đầu đến cuối chạy với LLM thật', [
    'Input: câu hỏi tự nhiên của chủ xe.',
    'Xử lý: agent LangGraph + Gemini gọi tool tra bảo dưỡng, dự toán, lịch trống, đề xuất đặt lịch.',
    'Output: câu trả lời từ dữ liệu thật, thẻ đề xuất, rồi lịch hẹn mà xưởng hoàn tất.',
    'Con người luôn là người xác nhận: agent không tự đặt lịch.',
  ], 9000)
  await finish(three, '3-result')
  assemble(`${out}/ev-care-mvp-demo-llm.mp4`)
  if (failures.length) throw new Error(failures.join('; '))
  console.log('MVP video recorded:', JSON.stringify(result))
} catch (error) {
  console.error(error.message)
  process.exitCode = 1
} finally {
  await browser.close()
  // Login popups record their own clips; only the three named segments belong in the video.
  for (const file of await readdir(out)) if (file.startsWith('page@')) await rm(`${out}/${file}`)
  await writeFile(`${out}/timeline.json`, JSON.stringify({ result, segments, timeline, browserErrors: failures }, null, 2))
}
