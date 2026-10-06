/**
 * Device position for the quick-booking chip (us-061 BR-1505). Asks the browser only because the
 * owner just tapped the chip; any refusal, timeout or missing API resolves `null` silently so the
 * backend falls back to the profile location.
 */
export function getDeviceLocation(timeoutMs = 5_000): Promise<{ lat: number; lng: number } | null> {
  if (typeof navigator === 'undefined' || !('geolocation' in navigator)) return Promise.resolve(null)
  return new Promise(resolve => {
    const timer = window.setTimeout(() => resolve(null), timeoutMs + 500)
    navigator.geolocation.getCurrentPosition(
      position => {
        window.clearTimeout(timer)
        resolve({ lat: position.coords.latitude, lng: position.coords.longitude })
      },
      () => {
        window.clearTimeout(timer)
        resolve(null)
      },
      { timeout: timeoutMs, maximumAge: 600_000 },
    )
  })
}
