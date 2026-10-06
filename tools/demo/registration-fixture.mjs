/** Arrange synthetic accounts for booking tests; registration itself is tested through UI separately. */
export async function completeRegistration(page, portal = 'owner') {
  await page.evaluate(async portal => {
    const { getIdToken } = await import('/src/features/auth/firebase.ts')
    const base = portal === 'owner' ? '' : '/workshop-owner'
    async function request(path, method = 'GET', body) {
      const response = await fetch(`/api/v1${base}${path}`, { method,
        headers: { Authorization: `Bearer ${await getIdToken()}`, 'Content-Type': 'application/json', 'Idempotency-Key': `registration-${portal}` },
        ...(body ? { body: JSON.stringify(body) } : {}) })
      if (!response.ok) throw new Error(`Registration fixture: ${response.status} ${path}`)
      return (await response.json()).data
    }
    const snapshot = await request('/onboarding')
    if (snapshot.onboarding.status === 'ACTIVE') return
    if (!snapshot.onboarding.profileCompleted) {
      await request('/onboarding/profile', 'PUT', { fullName: 'Minh Anh', phoneNumber: '0901234567', nationalId: '000000001234',
        personalDataConsent: { granted: true, policyVersion: '2026-09' },
        ...(portal === 'owner' ? { dateOfBirth: null, location: { addressLine: '123 Đường Demo', province: 'Hà Nội', source: 'MANUAL' } } : {}) })
    }
    const consent = { granted: true, policyVersion: '2026-09' }
    await request(portal === 'owner' ? '/onboarding/vehicle-verification' : '/onboarding/workshop-verification', 'POST',
      portal === 'owner' ? { vin: 'VF6ECO20240000001', licensePlate: '51A-11111', modelId: 'MDL-02', manufactureYear: 2024, oemDataSharingConsent: consent }
      : { address: '123 Đường Demo', latitude: null, longitude: null, hotline: '0901234567', totalTechnicians: 2, emergencySlotsReserved: 0,
        operatingHours: Array.from({ length: 7 }, (_, index) => ({ dayOfWeek: index + 1, isClosed: false, openTime: '08:00', closeTime: '18:00' })), oemDataSharingConsent: consent })
  }, portal)
  await page.reload()
  await page.getByRole('heading', { name: /Xin chào/ }).waitFor()
}
