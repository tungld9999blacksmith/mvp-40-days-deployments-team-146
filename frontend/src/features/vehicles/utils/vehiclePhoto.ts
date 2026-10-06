/**
 * Photo of each VinFast model (from vinfastauto.com), shown on "Xe của tôi" for the model the owner
 * declared at onboarding. Files live in public/vehicles/; a model without an entry shows the placeholder.
 */
const PHOTO_FILES: Record<string, string> = {
  vf2: 'vf2.webp',
  vf3: 'vf3.webp',
  vf5: 'vf5.webp',
  vf6: 'vf6.webp',
  vf7: 'vf7.webp',
  vf8: 'vf8.webp',
  vf9: 'vf9.webp',
  vfe34: 'vfe34.webp',
}

const MODEL_KEYS = ['vf2', 'vf3', 'vf5', 'vf6', 'vf7', 'vf8', 'vf9', 'vfe34']

/** "VF 6", "VF6 Plus", "VinFast VF e34", "VFE34" → "vf6" / "vfe34"; null when it is not a known model. */
export function vehicleModelKey(value: string | null | undefined): string | null {
  if (!value) return null
  const match = /\bvf\s*-?\s*(e\s*34|\d)\b/i.exec(value)
  if (!match) return null
  const key = `vf${match[1].replace(/\s+/g, '').toLowerCase()}`
  return MODEL_KEYS.includes(key) ? key : null
}

/** URL of the model photo, or null. The backend's modelId is an opaque code (MDL-01), so the name is tried first. */
export function vehiclePhotoSrc(
  modelName: string | null | undefined,
  modelId?: string | null,
  files: Record<string, string> = PHOTO_FILES,
): string | null {
  const key = vehicleModelKey(modelName) ?? vehicleModelKey(modelId)
  const file = key ? files[key] : undefined
  return file ? `/vehicles/${file}` : null
}
