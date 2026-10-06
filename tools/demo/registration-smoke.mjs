import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'

const base = process.env.DEMO_FRONTEND_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const failures = []
const result = {}
await mkdir('artifacts', { recursive: true })
async function signIn(page, uid, email) {
  await page.evaluate(async ({ uid, email }) => {
    const { getFirebaseAuth } = await import('/src/features/auth/firebase.ts')
    const { GoogleAuthProvider, signInWithCredential } = await import('/node_modules/.vite/deps/firebase_auth.js')
    await signInWithCredential(getFirebaseAuth(), GoogleAuthProvider.credential(JSON.stringify({ sub: uid, email, email_verified: true, name: uid })))
  }, { uid, email })
}
async function profile(page) {
  await page.getByLabel('Họ tên', { exact: false }).fill('Nguyễn Minh Anh')
  await page.getByLabel('Số điện thoại', { exact: false }).fill('0901234567')
  await page.getByLabel('Số CCCD', { exact: false }).fill('000000001234')
}
async function screenshot(page, name) {
  await page.screenshot({ path: `artifacts/registration-${name}.png`, fullPage: true })
}
let page
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  page = await context.newPage()
  page.on('pageerror', e => failures.push(e.message))
  await page.goto(base)
  await screenshot(page, 'login')
  const uid = `registration-driver-${Date.now()}`
  await signIn(page, uid, `${uid}@example.com`)
  await page.waitForURL('**/onboarding/profile')
  await page.getByRole('heading', { name: 'Thông tin cá nhân', exact: true }).waitFor()
  await profile(page)
  await page.getByLabel('Địa chỉ', { exact: false }).fill('123 Đường Demo')
  await page.getByLabel('Tỉnh / thành phố', { exact: false }).selectOption('Hà Nội')
  await page.locator('label', { has: page.locator('input[type=checkbox]') }).click()
  await screenshot(page, 'owner-profile')
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click()
  await page.waitForURL('**/onboarding/vehicle')
  await page.reload()
  await page.getByRole('heading', { name: 'Thông tin xe', exact: true }).waitFor()
  await page.getByLabel('Số VIN', { exact: false }).fill('VF6ECO20240000001')
  await page.getByRole('textbox', { name: /^Biển số/ }).fill('51A-11111')
  await page.getByLabel('Mẫu xe', { exact: false }).selectOption('MDL-02')
  await page.getByLabel('Năm sản xuất', { exact: false }).fill('2024')
  await page.locator('label', { has: page.locator('input[type=checkbox]') }).click()
  await screenshot(page, 'owner-vehicle')
  await page.getByRole('button', { name: 'Xác nhận & Xác thực', exact: true }).click()
  await page.waitForURL('**/onboarding/success')
  await page.getByRole('heading', { name: 'Xác thực xe thành công', exact: true }).waitFor()
  await screenshot(page, 'owner-success')
  await page.reload()
  await page.getByRole('heading', { name: 'Xác thực xe thành công', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Vào trang chủ', exact: true }).click()
  await page.waitForURL('**/dashboard')
  result.ownerRegistrationAndResume = true
  await context.close()

  const workshopUid = `registration-shop-${Date.now()}`
  const seedContext = await browser.newContext()
  const seed = await seedContext.newPage()
  await seed.goto(base)
  await signIn(seed, workshopUid, 'workshop1@example.com')
  await seed.waitForURL('**/onboarding/profile')
  await seedContext.close()
  const shopContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  page = await shopContext.newPage()
  page.on('pageerror', e => failures.push(e.message))
  await page.goto(`${base}/workshop/login`)
  await screenshot(page, 'workshop-login')
  const popupPromise = page.waitForEvent('popup')
  await page.getByRole('button', { name: /Google/ }).click()
  const popup = await popupPromise
  await popup.waitForLoadState('load')
  await page.waitForFunction(() => [...document.querySelectorAll('iframe')].some(f => f.src.includes('/emulator/auth/iframe')))
  await popup.waitForTimeout(1000)
  await popup.locator('.js-reuse-account', { hasText: workshopUid }).first().click()
  await page.waitForURL('**/workshop/onboarding/profile')
  await profile(page)
  await page.locator('label', { has: page.locator('input[type=checkbox]') }).click()
  await screenshot(page, 'workshop-profile')
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click()
  await page.waitForURL('**/workshop/onboarding/operations')
  await page.reload()
  await page.getByRole('heading', { name: 'Vận hành xưởng', exact: true }).waitFor()
  await page.getByLabel('Địa chỉ xưởng', { exact: false }).fill('123 Đường Demo')
  await page.getByLabel('Hotline xưởng', { exact: false }).fill('0901234567')
  await page.getByLabel('Số kỹ thuật viên mỗi ca', { exact: false }).fill('2')
  await page.locator('label', { hasText: 'Tôi đồng ý chia sẻ Gmail' }).click()
  await screenshot(page, 'workshop-operations')
  await page.getByRole('button', { name: 'Gửi xác thực', exact: true }).click()
  await page.waitForURL('**/workshop/onboarding/success')
  await page.getByRole('heading', { name: 'Xác thực chủ xưởng thành công', exact: true }).waitFor()
  await page.getByText('0901234567', { exact: true }).waitFor()
  await screenshot(page, 'workshop-success')
  await page.reload()
  await page.getByRole('heading', { name: 'Xác thực chủ xưởng thành công', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Vào Dashboard', exact: true }).click()
  await page.waitForURL('**/technician')
  result.workshopRegistrationAndResume = true
  await shopContext.close()
  if (failures.length) throw new Error(failures.join('; '))
  console.log('Owner/workshop registration forms, backend state, reload and dashboards: PASS')
} catch (error) {
  failures.push(error.message)
  if (page && !page.isClosed()) await screenshot(page, 'failure')
  console.error(error.message)
  process.exitCode = 1
} finally {
  await browser.close()
  await writeFile('artifacts/registration-results.json', JSON.stringify({ result, failures }, null, 2))
}
