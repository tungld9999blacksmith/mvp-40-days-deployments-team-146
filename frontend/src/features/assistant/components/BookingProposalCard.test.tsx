import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { BookingProposalCard as Card } from '../types'
import BookingProposalCard from './BookingProposalCard'

const card: Card = {
  type: 'BOOKING_PROPOSAL',
  version: 1,
  proposalId: 'proposal-1',
  vehicle: { userVehicleId: 'vehicle-1', modelName: 'VF 6', trim: 'Plus', licensePlateMasked: '30A***45' },
  milestone: null,
  reason: 'Gói được tạo từ mốc bảo dưỡng đã xác minh.',
  locationBasis: 'NONE',
  locationLabel: null,
  primary: {
    optionId: 'opt-1',
    workshopId: 'workshop-1',
    workshopName: 'VinFast Thanh Xuân',
    address: 'Hà Nội',
    region: 'Hà Nội',
    distanceKm: null,
    isPreferred: false,
    date: '2026-10-15',
    timeSlot: '14:00',
    estimate: null,
    maintenancePackage: {
      packageCode: 'BALANCED',
      name: 'Cân bằng',
      items: [
        {
          itemCode: 'BRAKE_INSPECTION',
          itemName: 'Kiểm tra hệ thống phanh',
          tier: 'REQUIRED',
          price: '350000',
          covered: false,
          priceSource: 'WORKSHOP_PRICE',
          durationMinutes: 30,
          seenInServiceHistory: false,
        },
      ],
      itemCodes: ['BRAKE_INSPECTION'],
      omittedItemCodes: [],
      estimatedTotal: '350000',
      estimatedDurationMinutes: 30,
      constraintStatus: 'FITS',
    },
  },
  alternatives: [],
  expiresAt: '2026-10-15T08:00:00Z',
  status: 'PROPOSED',
  booking: null,
}

describe('BookingProposalCard maintenance package', () => {
  it('shows the selected package, its verified scope and estimate', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <BookingProposalCard card={card} confirmationHref="/booking/proposal" />
      </MemoryRouter>,
    )

    expect(html).toContain('Gói Cân bằng')
    expect(html).toContain('BALANCED')
    expect(html).toContain('Kiểm tra hệ thống phanh')
    expect(html).toContain('Bắt buộc')
    expect(html).toContain('350.000')
    expect(html).toContain('30 phút dự kiến')
  })
})
