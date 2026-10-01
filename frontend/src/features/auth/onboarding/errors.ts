import { isApiError, NETWORK_ERROR, TIMEOUT_ERROR } from '@/shared/api/client'

/**
 * Vietnamese inline message for a backend `INVALID_FIELD_FORMAT` field. The backend
 * `error.message` is in English, so the UI keeps the spec wording instead.
 */
const FIELD_MESSAGES: Record<string, string> = {
  fullName: 'Họ tên không hợp lệ.',
  phoneNumber: 'Số điện thoại không hợp lệ.',
  nationalId: 'Số CCCD phải gồm đúng 12 chữ số.',
  dateOfBirth: 'Ngày sinh không hợp lệ.',
  location: 'Địa chỉ không hợp lệ.',
  'location.addressLine': 'Vui lòng nhập địa chỉ (tối thiểu 5 ký tự).',
  'location.province': 'Vui lòng chọn tỉnh/thành phố.',
  vin: 'Số VIN phải gồm 17 ký tự chữ và số.',
  licensePlate: 'Biển số xe không hợp lệ.',
  modelId: 'Vui lòng chọn mẫu xe.',
  manufactureYear: 'Năm sản xuất không hợp lệ.',
}

/** Maps a server field error to the form key that shows it. */
export function formKeyForField(field: string): string {
  if (field.startsWith('location.addressLine')) return 'addressLine'
  if (field.startsWith('location.province')) return 'province'
  if (field.startsWith('location')) return 'addressLine'
  return field
}

export function fieldMessage(field: string): string {
  return FIELD_MESSAGES[field] ?? 'Dữ liệu không hợp lệ.'
}

/** Generic message for a failed submit that is not a field error. */
export function submitErrorMessage(error: unknown): string {
  if (isApiError(error) && (error.code === NETWORK_ERROR || error.code === TIMEOUT_ERROR)) {
    return 'Không có kết nối mạng. Vui lòng kiểm tra và thử lại.'
  }
  if (isApiError(error, 'INVALID_REQUEST')) return 'Dữ liệu gửi lên không hợp lệ. Vui lòng kiểm tra lại.'
  return 'Không thể lưu thông tin. Vui lòng thử lại.'
}
