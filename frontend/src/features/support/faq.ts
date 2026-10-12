/**
 * "Câu hỏi thường gặp" on the Hỗ trợ page. Every answer restates a rule the app already
 * enforces (PRD F6/F6b/F7, us-029, us-053) — no promise the backend does not keep.
 */

export interface FaqItem {
  id: string
  question: string
  answer: string
  /** In-app page that answers the question by doing it. */
  link?: { to: string; label: string }
}

export interface FaqTopic {
  id: string
  title: string
  items: FaqItem[]
}

export const FAQ_TOPICS: FaqTopic[] = [
  {
    id: 'booking',
    title: 'Đặt lịch',
    items: [
      {
        id: 'booking-hold',
        question: 'Bấm Xác nhận xong thì lịch hẹn đã chắc chắn chưa?',
        answer:
          'Chỗ của bạn được giữ ngay. Xưởng tự động xác nhận thì lịch chuyển sang "Đã xác nhận" luôn; xưởng xác nhận thủ công thì lịch ở trạng thái "Chờ xưởng xác nhận". Nếu xưởng không phản hồi trong 12 giờ (hoặc trước giờ hẹn nếu sớm hơn), lịch tự huỷ và bạn nhận thông báo.',
        link: { to: '/bookings', label: 'Xem lịch hẹn của tôi' },
      },
      {
        id: 'booking-undo',
        question: 'Tôi lỡ đặt nhầm, có huỷ ngay được không?',
        answer: 'Trong 10 phút đầu sau khi giữ chỗ, bạn tự huỷ được ngay trên trang lịch hẹn và chỗ được trả lại cho xưởng.',
      },
      {
        id: 'booking-one-open',
        question: 'Sao tôi không đặt thêm lịch cho cùng một xe được?',
        answer: 'Mỗi xe chỉ có một lịch hẹn đang mở. Muốn đổi ngày giờ, hãy dùng "Đổi lịch" trên lịch hẹn hiện có.',
      },
    ],
  },
  {
    id: 'change',
    title: 'Đổi hoặc huỷ lịch',
    items: [
      {
        id: 'change-reschedule',
        question: 'Tôi đổi lịch được mấy lần?',
        answer:
          'Tối đa 2 lần cho mỗi lịch hẹn và phải trước giờ hẹn ít nhất 60 phút. Ứng dụng kiểm tra khung giờ mới còn chỗ rồi mới trả khung cũ. Quá hạn này, vui lòng gọi xưởng.',
      },
      {
        id: 'change-cancel',
        question: 'Huỷ lịch hẹn thế nào?',
        answer:
          'Mở lịch hẹn và bấm "Huỷ lịch" khi nút này còn hiện. Chỗ được giải phóng ngay. Thông báo nhắc lịch (gửi trước giờ hẹn 24 giờ) cũng mở thẳng lịch hẹn để bạn xác nhận, đổi hoặc huỷ.',
        link: { to: '/bookings', label: 'Mở lịch hẹn của tôi' },
      },
    ],
  },
  {
    id: 'visit',
    title: 'Đến xưởng',
    items: [
      {
        id: 'visit-checkin',
        question: 'Đến xưởng tôi cần làm gì?',
        answer:
          'Khi lịch đã được xác nhận, trang lịch hẹn có mã lịch hẹn và mã QR. Đưa mã QR cho xưởng quét để check-in, kèm các giấy tờ cần mang ghi trên lịch hẹn.',
      },
      {
        id: 'visit-progress',
        question: 'Xem tiến độ sửa xe ở đâu?',
        answer: 'Sau khi check-in, trang lịch hẹn hiện tiến độ do xưởng cập nhật cho tới khi hoàn tất.',
      },
    ],
  },
  {
    id: 'cost',
    title: 'Chi phí và bảo hành',
    items: [
      {
        id: 'cost-estimate',
        question: 'Chi phí trong ứng dụng có phải giá cuối cùng không?',
        answer:
          'Đó là chi phí ước tính theo mốc bảo dưỡng và bảng giá của xưởng. Hạng mục trong bảo hành được tách riêng và không cộng vào tổng. Giá cuối cùng do xưởng chốt khi làm xe.',
        link: { to: '/estimate', label: 'Xem chi phí bảo dưỡng' },
      },
      {
        id: 'cost-warranty',
        question: 'Hạng mục nào được bảo hành?',
        answer:
          'Hỏi AI Trợ lý: câu trả lời lấy từ tài liệu chính hãng và ghi rõ nguồn. Tài liệu không nêu thì trợ lý sẽ nói chưa có nguồn. Trường hợp tranh chấp bảo hành, vui lòng liên hệ xưởng.',
        link: { to: '/ai', label: 'Hỏi AI Trợ lý' },
      },
    ],
  },
  {
    id: 'reminders',
    title: 'Nhắc lịch và thông báo',
    items: [
      {
        id: 'reminders-when',
        question: 'Khi nào tôi được nhắc bảo dưỡng?',
        answer:
          'Mặc định trước ngày đến hạn 2 ngày, hoặc khi xe còn từ 500 km trở xuống là tới mốc. Bạn đổi số ngày (0–30) hoặc tắt nhắc trong Cài đặt thông báo. Lịch hẹn còn được nhắc trước giờ hẹn 24 giờ.',
        link: { to: '/notifications/settings', label: 'Mở cài đặt thông báo' },
      },
      {
        id: 'reminders-channel',
        question: 'Tôi nhận thông báo qua kênh nào?',
        answer: 'Mọi thông báo nằm trong mục Thông báo của ứng dụng. Email nhắc bảo dưỡng có thể bật trong Cài đặt thông báo khi kênh này được hỗ trợ và email đăng nhập đã xác minh. Zalo, Telegram và SMS sẽ có sau.',
        link: { to: '/notifications/settings', label: 'Mở cài đặt thông báo' },
      },
    ],
  },
]
