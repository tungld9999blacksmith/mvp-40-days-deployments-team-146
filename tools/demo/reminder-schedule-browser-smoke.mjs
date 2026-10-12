// Real settings/detail UI and HTTP routes, disposable data and mock email only.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.REMINDER_UI_URL || 'http://127.0.0.1:18772'
const artifacts = path.resolve(import.meta.dirname, '../../data/verification/driving-habit/latest/browser/p2')
await mkdir(artifacts, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const results = [], blocked = []
async function api(url, method = 'GET') {
  const response = await fetch(`${base}/api/v1${url}`, { method, headers: { Authorization: 'Bearer fixture-owner' } })
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
    const fixture = await api('/__fixture/reset?scenario=available', 'POST')
    const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme })
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin === new URL(base).origin) return route.continue()
      blocked.push(new URL(route.request().url()).hostname)
      return route.abort()
    })
    await context.addInitScript(t => document.addEventListener('DOMContentLoaded', () => { document.documentElement.dataset.theme = t }), theme)
    const page = await context.newPage(), errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.goto(`${base}/tests/browser/index.html`)
    const timeSwitch = page.getByRole('switch', { name: 'Chọn giờ nhận nhắc', exact: true })
    await timeSwitch.focus()
    await page.keyboard.press('Space')
    const at = new Date(new Date(fixture.clock).getTime() + 60 * 60 * 1000)
    const selected = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(at)
    await page.getByLabel('Giờ nhận', { exact: true }).fill(selected)
    await page.getByRole('switch', { name: 'Bật giờ yên lặng', exact: true }).click()
    // Use a window after the selected hour so the deterministic fixture slot is not moved.
    const nextHour = String((Number(selected.slice(0, 2)) + 2) % 24).padStart(2, '0')
    const endHour = String((Number(selected.slice(0, 2)) + 3) % 24).padStart(2, '0')
    await page.getByLabel('Bắt đầu', { exact: true }).fill(`${nextHour}:00`)
    await page.getByLabel('Kết thúc', { exact: true }).fill(`${endHour}:00`)
    await page.getByRole('checkbox', { name: 'Email', exact: true }).focus()
    await page.keyboard.press('Space')
    assert.equal((await api('/notification-settings')).data.preferredSendTime, null)
    await page.getByRole('button', { name: 'Lưu', exact: true }).click()
    await page.getByText('Đã lưu cài đặt thông báo.', { exact: false }).waitFor()
    const saved = (await api('/notification-settings')).data
    assert.equal(saved.preferredSendTime, selected)
    assert.deepEqual(saved.quietHours, { start: `${nextHour}:00`, end: `${endHour}:00` })
    await audit(page)
    await page.screenshot({ path: path.join(artifacts, `settings-${width}-${theme}.png`), fullPage: true })
    await page.reload()
    assert.equal(await page.getByLabel('Giờ nhận', { exact: true }).inputValue(), selected)
    const reminder = await api('/__fixture/remind', 'POST')
    const before = (await api(`/notifications/reminders/${reminder.reminderId}`)).data
    assert.equal(before.deliveries.length, 1)
    assert.equal(before.deliveries[0].attempts, 0)
    assert(before.deliveries[0].nextEligibleSendAt)
    assert.equal((await api('/__fixture/dispatch', 'POST')).sent, 0)
    await page.goto(`${base}/tests/browser/index.html?reminderId=${reminder.reminderId}`)
    await page.getByText('Có thể gửi từ:', { exact: false }).waitFor()
    await audit(page)
    await api('/__fixture/advance?minutes=60', 'POST')
    assert.equal((await api('/__fixture/dispatch', 'POST')).sent, 1)
    assert.equal((await api('/__fixture/dispatch', 'POST')).sent, 0)
    const after = (await api(`/notifications/reminders/${reminder.reminderId}`)).data.deliveries[0]
    assert.equal(after.status, 'SENT')
    assert.equal(after.attempts, 1)
    assert.equal(after.mode, 'mock')
    assert.deepEqual(errors, [])
    results.push({ width, theme, saveOnly: true, persistedAfterReload: true, feedBeforeSend: true, noEarlySend: true, dueDispatchOnce: true, keyboardSwitch: true, axeViolations: 0, horizontalOverflow: false })
    await context.close()
  }
  await writeFile(path.join(artifacts, 'verification.json'), JSON.stringify({ status: 'passed', dataset: 'disposable-fixture', externalProviderCalls: 0, externalRequestsBlocked: blocked, results }, null, 2))
  console.log(JSON.stringify({ status: 'passed', scenarios: results.length, externalProviderCalls: 0 }))
} finally {
  await browser.close()
}
