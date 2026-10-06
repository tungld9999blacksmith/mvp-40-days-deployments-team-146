import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { completeRegistration } from './registration-fixture.mjs'
const base = process.env.DEMO_FRONTEND_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'chrome', headless: true })
await mkdir('artifacts', { recursive: true })
const results = []
const failures = []
try {
  for (const [uid, email, routes] of [
    ['showroom-driver', 'showroom-driver@example.com', ['/dashboard', '/vehicle', '/bookings', '/booking/workshops', '/estimate', '/ai', '/history', '/notifications', '/notifications/settings']],
    ['showroom-shop', 'workshop1@example.com', ['/technician', '/technician/board', '/technician/check-in', '/technician/capacity', '/technician/settings/booking', '/technician/notifications']],
  ]) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const page = await context.newPage()
    page.on('pageerror', error => failures.push(error.message))
    const apiErrors = []
    page.on('response', response => { if (response.url().includes('/api/v1/') && response.status() >= 400) apiErrors.push(`${response.status()} ${response.url()}`) })
    await page.goto(base)
    await page.evaluate(async ({ uid, email }) => {
      const { getFirebaseAuth } = await import('/src/features/auth/firebase.ts')
      const { GoogleAuthProvider, signInWithCredential } = await import('/node_modules/.vite/deps/firebase_auth.js')
      await signInWithCredential(getFirebaseAuth(), GoogleAuthProvider.credential(JSON.stringify({ sub: uid, email, email_verified: true, name: 'Minh Anh' })))
    }, { uid, email })
    await page.waitForURL(url => ['/dashboard', '/onboarding/profile', '/onboarding/vehicle'].includes(url.pathname), { timeout: 30000 })
    await completeRegistration(page)
    await page.goto(`${base}/dashboard`)
    if (email === 'workshop1@example.com') {
      await page.goto(`${base}/workshop/login`)
      const popupPromise = page.waitForEvent('popup')
      await page.getByRole('button', { name: /Google/ }).click()
      const popup = await popupPromise
      await popup.waitForLoadState('load')
      await page.waitForFunction(() => [...document.querySelectorAll('iframe')].some(f => f.src.includes('/emulator/auth/iframe')))
      await popup.waitForTimeout(1000)
      await popup.locator('.js-reuse-account', { hasText: email }).first().click()
      await page.waitForURL(url => url.pathname === '/technician' || url.pathname.startsWith('/workshop/onboarding/'), { timeout: 30000 })
      await completeRegistration(page, 'workshop')
      await page.goto(`${base}/technician`)
    }
    for (const route of routes) {
      await page.goto(base + route)
      await page.waitForTimeout(1400)
      if (route === '/dashboard') {
        await page.getByRole('button', { name: 'Dừng tự chuyển', exact: true }).click()
        await page.getByRole('button', { name: 'Xem: Hạn bảo dưỡng', exact: true }).click()
        await page.waitForTimeout(800)
      }
      await page.screenshot({ path: `artifacts/showroom-${route.replaceAll('/', '-').slice(1)}.png`, fullPage: true })
      results.push({ route, background: await page.evaluate(() => getComputedStyle(document.body).backgroundColor), heading: await page.locator('h1').allTextContents() })
    }
    if (apiErrors.length) failures.push(...apiErrors)
    await context.close()
  }
} catch (error) { failures.push(error.message) }
finally { await browser.close(); await writeFile('artifacts/showroom-results.json', JSON.stringify({ results, failures }, null, 2)) }
if (failures.length) { console.error(failures.join('\n')); process.exitCode = 1 }
else console.log('Showroom UI, owner/workshop routes and real API reads: PASS')
