import { describe, expect, it } from 'vitest'
import { vehicleModelKey, vehiclePhotoSrc } from './vehiclePhoto'

describe('vehicleModelKey', () => {
  it('reads the model from display names and ids', () => {
    expect(vehicleModelKey('VF 6')).toBe('vf6')
    expect(vehicleModelKey('VF5 Plus')).toBe('vf5')
    expect(vehicleModelKey('VinFast VF 9')).toBe('vf9')
    expect(vehicleModelKey('VF e34')).toBe('vfe34')
    expect(vehicleModelKey('VFE34')).toBe('vfe34')
    expect(vehicleModelKey('VF-8')).toBe('vf8')
    expect(vehicleModelKey('VF 2')).toBe('vf2')
  })

  it('returns null for unknown or missing models', () => {
    expect(vehicleModelKey(null)).toBeNull()
    expect(vehicleModelKey('MDL-01')).toBeNull()
    expect(vehicleModelKey('VF 4')).toBeNull()
    expect(vehicleModelKey('Limo Green')).toBeNull()
  })
})

describe('vehiclePhotoSrc', () => {
  const files = { vf7: 'vf7.webp', vf3: 'vf3.png' }

  it('prefers the model name, then falls back to the model id', () => {
    expect(vehiclePhotoSrc('VF 7', 'MDL-04', files)).toBe('/vehicles/vf7.webp')
    expect(vehiclePhotoSrc(null, 'VF3', files)).toBe('/vehicles/vf3.png')
    expect(vehiclePhotoSrc(null, 'MDL-01', files)).toBeNull()
  })

  it('returns null when the model has no photo yet', () => {
    expect(vehiclePhotoSrc('VF 9', null, files)).toBeNull()
  })
})
