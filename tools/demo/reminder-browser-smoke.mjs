// Real product components + real local HTTP services; all business data is fixture data.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'

const base = process.env.REMINDER_UI_URL || 'http://127.0.0.1:18762'
const artifacts = path.resolve(import.meta.dirname, '../../data/verification/driving-habit/latest/browser/p1')
await mkdir(artifacts, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const results = []
const external = []
async function api(url, method = 'GET') {
  const response = await fetch(`${base}/api/v1${url}`, { method, headers: { Authorization: 'Bearer fixture-owner' } })
  assert.equal(response.status, 200, `${method} ${url}: ${await response.clone().text()}`)
  return response.json()
}
async function audit(page, name) {
  await page.addScriptTag({ path: path.resolve(import.meta.dirname, 'node_modules/axe-core/axe.min.js') })
  const violations = await page.evaluate(async () => (await window.axe.run(document, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
  })).violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => n.target) })))
  assert.deepEqual(violations, [], `${name}: ${JSON.stringify(violations)}`)
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}: horizontal overflow`)
}
try {
  for (const width of [390, 1280]) for (const theme of ['light', 'dark']) {
    await api('/__fixture/reset', 'POST')
    const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme })
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin === new URL(base).origin) return route.continue()
      external.push(new URL(route.request().url()).hostname)
      return route.abort()
    })
    await context.addInitScript(t => { document.addEventListener('DOMContentLoaded', () => { document.documentElement.dataset.theme = t }) }, theme)
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.goto(`${base}/tests/browser/index.html`)
    const toggle = page.getByRole('switch', { name: 'Nhắc theo mức sử dụng xe', exact: true })
    await toggle.waitFor()
    assert.equal(await toggle.getAttribute('aria-checked'), 'false')
    await toggle.focus()
    await page.keyboard.press('Space')
    assert.equal((await api('/notification-settings')).data.personalizedRemindersEnabled, false)
    await page.getByRole('button', { name: 'Lưu', exact: true }).click()
    await page.getByText('Đã lưu cài đặt thông báo.', { exact: false }).waitFor()
    assert.equal((await api('/notification-settings')).data.personalizedRemindersEnabled, true)
    await audit(page, `settings-${width}-${theme}`)
    await page.screenshot({ path: path.join(artifacts, `settings-${width}-${theme}.png`), fullPage: true })
    await page.getByRole('link', { name: 'Xe', exact: true }).click()
    await page.getByText('200 km/ngày', { exact: true }).waitFor()
    await page.getByText('Nên lên kế hoạch bảo dưỡng', { exact: false }).waitFor()
    await audit(page, `vehicle-${width}-${theme}`)
    await page.screenshot({ path: path.join(artifacts, `vehicle-${width}-${theme}.png`), fullPage: true })
    const reminder = await api('/__fixture/remind', 'POST')
    assert(reminder.reminderId)
    await page.goto(`${base}/tests/browser/index.html?reminderId=${reminder.reminderId}`)
    await page.getByText('Mức sử dụng tại lúc tạo lời nhắc', { exact: true }).waitFor()
    const bookingHref = await page.getByRole('link', { name: 'Đặt lịch theo mốc hiện tại' }).getAttribute('href')
    assert.equal(new URL(bookingHref, base).searchParams.get('sourceReminderId'), reminder.reminderId)
    await audit(page, `detail-${width}-${theme}`)
    await page.screenshot({ path: path.join(artifacts, `detail-${width}-${theme}.png`), fullPage: true })
    await page.getByRole('link', { name: 'Cài đặt', exact: true }).click()
    await page.getByRole('button', { name: 'Xoá dữ liệu suy ra đã lưu' }).click()
    const dialog = page.getByRole('alertdialog', { name: 'Xoá dữ liệu cá nhân hoá?' })
    await dialog.waitFor()
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('Tab')
      assert(await page.evaluate(() => Boolean(document.activeElement?.closest('[role="alertdialog"]'))))
    }
    await audit(page, `erase-dialog-${width}-${theme}`)
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
    await page.getByRole('button', { name: 'Xoá dữ liệu suy ra đã lưu' }).click()
    await dialog.getByRole('button', { name: 'Xoá dữ liệu suy ra', exact: true }).click()
    await page.getByText('Đã tắt cá nhân hoá và xoá dữ liệu suy ra đã lưu.', { exact: true }).waitFor()
    assert.equal((await api('/notification-settings')).data.personalizedRemindersEnabled, false)
    assert.equal((await api(`/notifications/reminders/${reminder.reminderId}`)).data.details.personalization, undefined)
    await page.getByRole('link', { name: 'Xe', exact: true }).click()
    await page.getByRole('link', { name: 'Bật nhắc theo mức sử dụng xe', exact: true }).waitFor()
    assert.equal(await page.getByText('200 km/ngày', { exact: true }).count(), 0)
    assert.deepEqual(errors, [])
    results.push({ width, theme, consentSave: true, forecast: true, snapshot: true, bookingOriginLink: true, keyboardDialog: true, erasure: true, axeViolations: 0, horizontalOverflow: false })
    await context.close()
  }
  for (const scenario of ['insufficient', 'static', 'shadow']) {
    await api(`/__fixture/reset?scenario=${scenario}`, 'POST')
    const page = await browser.newPage({ viewport: { width: 390, height: 900 } })
    await page.route('**/*', route => {
      if (new URL(route.request().url()).origin === new URL(base).origin) return route.continue()
      external.push(new URL(route.request().url()).hostname)
      return route.abort()
    })
    await page.goto(`${base}/tests/browser/index.html?screen=vehicle`)
    const expected = scenario === 'insufficient' ? 'Chưa đủ lịch sử số km' : scenario === 'static' ? 'Nguồn số km hiện tại' : '200 km/ngày'
    await page.getByText(expected, { exact: false }).waitFor()
    assert.equal((await api('/__fixture/remind', 'POST')).reminderId, null)
    await audit(page, scenario)
    results.push({ scenario, fixedPolicyPreserved: true, axeViolations: 0 })
    await page.close()
  }
  await writeFile(path.join(artifacts, 'verification.json'), JSON.stringify({ status: 'passed', dataset: 'disposable-fixture', providerCalls: 0, externalRequestsBlocked: external, results }, null, 2))
  console.log(JSON.stringify({ status: 'passed', scenarios: results.length, providerCalls: 0 }))
} finally {
  await browser.close()
}
