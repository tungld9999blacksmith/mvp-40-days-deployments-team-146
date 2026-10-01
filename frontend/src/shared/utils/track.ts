/**
 * Analytics hook. The project has no analytics tool yet, so this is a no-op that
 * keeps the event names from the FE specs in one place.
 * Never pass personal data (email, phone, national id, VIN, plate, message text).
 */
export function track(_event: string, _props?: Record<string, string | number | boolean | null>): void {
  // Intentionally empty until an analytics tool is chosen.
}
