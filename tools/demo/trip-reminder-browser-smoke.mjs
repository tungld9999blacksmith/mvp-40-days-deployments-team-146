// Product UI + HTTP/domain services; disposable SQLite and mock email only.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.REMINDER_UI_URL || 'http://127.0.0.1:18772'
const artifacts = path.resolve(import.meta.dirname, '../../data/verification/driving-habit/latest/browser/p3')
await mkdir(artifacts, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const results = [], blocked = []
async function api(url, method = 'GET', body) {
  const response = await fetch(`${base}/api/v1${url}`, {
    method, headers: { Authorization: 'Bearer fixture-owner', 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  assert.equal(response.status, 200, `${method} ${url}: ${await response.clone().text()}`)
  return response.json()
}
async function audit(page) {
  await page.addScriptTag({ path: path.resolve(import.meta.dirname, 'node_modules/axe-core/axe.min.js') })
  const violations = await page.evaluate(async () => (await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } })).violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) })))
  assert.deepEqual(violations, [])
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'horizontal overflow')
}
try {
  for (const width of [390, 1280]) for (const theme of ['light', 'dark']) {
    const fixture = await api('/__fixture/reset?scenario=trip', 'POST')
    const tripUrl = `/user-vehicles/${fixture.vehicleId}/trip-plan`
    const maintenanceUrl = `/user-vehicles/${fixture.vehicleId}/maintenance-status`
    assert.equal((await api(tripUrl)).data, null)
    const observedBefore = (await api(maintenanceUrl)).data
    const selectedAt = new Date(new Date(fixture.clock).getTime() + 3600000)
    const selected = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(selectedAt)
    await api('/notification-settings', 'PUT', {
      remindersEnabled: true, reminderLeadDays: 7,
      preferredSendTime: selected, channels: [{ channel: 'EMAIL', enabled: true }],
    })
    const departure = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(new Date(fixture.clock).getTime() + 3 * 86400000))
    const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme })
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin === new URL(base).origin) return route.continue()
      blocked.push(new URL(route.request().url()).hostname)
      return route.abort()
    })
    await context.addInitScript(t => document.addEventListener('DOMContentLoaded', () => { document.documentElement.dataset.theme = t }), theme)
    const page = await context.newPage(), errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.goto(`${base}/tests/browser/index.html?screen=vehicle`)
    await page.getByLabel('Ngày khởi hành', { exact: true }).fill(departure)
    await page.getByLabel('Tổng quãng đường dự kiến', { exact: true }).fill('1500')
    const consent = page.getByRole('checkbox', { name: 'Nhắc bảo dưỡng trước chuyến đi này qua các kênh tôi đã bật', exact: true })
    await consent.focus()
    await page.keyboard.press('Space')
    assert.equal((await api(tripUrl)).data, null)
    await page.getByRole('button', { name: 'Lưu chuyến đi', exact: true }).click()
    await page.getByText('Đã lưu chuyến đi.', { exact: true }).waitFor()
    const saved = (await api(tripUrl)).data
    assert.equal(saved.distanceKm, 1500)
    assert.equal(saved.advice.status, 'MAINTENANCE_RECOMMENDED')
    assert.equal(saved.advice.projectedTripEndKm, 12300)
    assert.equal(saved.advice.projectedUsageBeforeDepartureKm, 0)
    assert.equal((await api('/notification-settings')).data.personalizedRemindersEnabled, false)
    const booking = page.getByRole('link', { name: 'Chọn lịch bảo dưỡng trước chuyến đi', exact: true })
    assert((await booking.getAttribute('href')).includes(fixture.vehicleId))
    await audit(page)
    await page.screenshot({ path: path.join(artifacts, `trip-${width}-${theme}.png`), fullPage: true })
    await page.reload()
    await page.getByRole('button', { name: 'Xoá chuyến đi', exact: true }).waitFor()
    assert.equal(await page.getByLabel('Ngày khởi hành', { exact: true }).inputValue(), departure)
    const reminder = await api('/__fixture/remind', 'POST')
    assert(reminder.reminderId)
    const detailUrl = `/notifications/reminders/${reminder.reminderId}`
    const before = (await api(detailUrl)).data
    assert.equal(before.details.trip.distanceKm, 1500)
    assert.equal(before.deliveries[0].attempts, 0)
    assert.equal((await api('/__fixture/dispatch', 'POST')).sent, 0)
    assert.equal((await api('/__fixture/remind', 'POST')).reminderId, reminder.reminderId)
    await page.goto(`${base}/tests/browser/index.html?reminderId=${reminder.reminderId}`)
    await page.getByText('Nhắc trước chuyến đi bạn khai báo ngày', { exact: false }).waitFor()
    await audit(page)
    await api('/__fixture/advance?minutes=60', 'POST')
    assert.equal((await api('/__fixture/dispatch', 'POST')).sent, 1)
    assert.equal((await api('/__fixture/dispatch', 'POST')).sent, 0)
    const sent = (await api(detailUrl)).data.deliveries[0]
    assert.equal(sent.status, 'SENT')
    assert.equal(sent.attempts, 1)
    assert.equal(sent.mode, 'mock')
    await page.goto(`${base}/tests/browser/index.html?screen=vehicle`)
    await page.getByRole('button', { name: 'Xoá chuyến đi', exact: true }).click()
    await page.getByText('Đã xoá chuyến đi và dừng lượt nhắc đang chờ liên quan.', { exact: true }).waitFor()
    assert.equal((await api(tripUrl)).data, null)
    const erased = (await api(detailUrl)).data
    assert.equal(erased.details.trip, undefined)
    assert.equal(erased.details.tripDeleted, true)
    assert.equal(erased.deliveries[0].status, 'SENT')
    const observedAfter = (await api(maintenanceUrl)).data
    assert.equal(observedAfter.odometer.odoKm, observedBefore.odometer.odoKm)
    assert.deepEqual(errors, [])
    results.push({ width, theme, saveOnly: true, persistedAfterReload: true, keyboardConsent: true,
      declaredTripWithoutUsageConsent: true, noEarlySend: true, mockDispatchOnce: true,
      stableReminderId: true, tripErasedReceiptRetained: true, axeViolations: 0, horizontalOverflow: false })
    await context.close()
  }
  await writeFile(path.join(artifacts, 'verification.json'), JSON.stringify({ status: 'passed', dataset: 'disposable-fixture', externalProviderCalls: 0, externalRequestsBlocked: blocked, results }, null, 2))
  console.log(JSON.stringify({ status: 'passed', scenarios: results.length, externalProviderCalls: 0 }))
} finally { await browser.close() }
