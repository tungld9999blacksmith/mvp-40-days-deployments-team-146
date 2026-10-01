import Button from '@/shared/ui/Button'

function GoogleMark() {
  // Monochrome outline mark (icons stay single-color per design style §5.7).
  return (
    <svg viewBox="0 0 24 24" className="w-4 h-4" aria-hidden fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M21 12.2c0-.7-.1-1.3-.2-1.9H12v3.6h5.1a4.4 4.4 0 0 1-1.9 2.9v2.4h3.1c1.8-1.7 2.7-4.1 2.7-7Z" />
      <path d="M12 21.5c2.6 0 4.7-.9 6.3-2.3l-3.1-2.4c-.9.6-1.9.9-3.2.9-2.5 0-4.6-1.7-5.3-3.9H3.5v2.5a9.5 9.5 0 0 0 8.5 5.2Z" />
      <path d="M6.7 13.8a5.7 5.7 0 0 1 0-3.6V7.7H3.5a9.5 9.5 0 0 0 0 8.6l3.2-2.5Z" />
      <path d="M12 6.3c1.4 0 2.6.5 3.6 1.4l2.7-2.7A9.5 9.5 0 0 0 3.5 7.7l3.2 2.5C7.4 8 9.5 6.3 12 6.3Z" />
    </svg>
  )
}

export default function GoogleSignInButton({
  onClick,
  loading,
  disabled,
}: {
  onClick: () => void
  loading?: boolean
  disabled?: boolean
}) {
  return (
    <Button
      size="lg"
      fullWidth
      onClick={onClick}
      loading={loading}
      loadingText="Đang đăng nhập..."
      disabled={disabled}
      icon={<GoogleMark />}
      aria-label="Đăng nhập bằng Google"
    >
      Tiếp tục với Google
    </Button>
  )
}
