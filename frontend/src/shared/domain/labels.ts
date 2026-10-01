/** Vietnamese labels for backend enums shared by several features. */

const WARRANTY_COMPONENTS: Record<string, string> = {
  BATTERY: 'Pin cao áp',
  MOTOR: 'Động cơ điện',
  CHASSIS: 'Khung gầm',
  ELECTRONICS: 'Điện tử',
}

export function warrantyComponentLabel(component: string): string {
  return WARRANTY_COMPONENTS[component] ?? component
}

/** VinFast VF6 Plus — skips missing parts. */
export function vehicleDisplayName(modelName: string | null | undefined, trim?: string | null): string {
  const parts = [modelName, trim].filter(Boolean)
  return parts.length ? `VinFast ${parts.join(' ')}` : 'Xe của bạn'
}
