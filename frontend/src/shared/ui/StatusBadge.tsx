export default function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    completed: { label: 'Hoàn thành', cls: 'text-emerald bg-emerald/10' },
    'due-soon': { label: 'DUE SOON', cls: 'text-warning bg-warning/10' },
    overdue: { label: 'OVERDUE', cls: 'text-error bg-error/10' },
    pending: { label: 'Chờ xử lý', cls: 'text-muted bg-card' },
  }
  const { label, cls } = map[status] ?? map.pending
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold font-mono uppercase tracking-wide ${cls}`}>
      {label}
    </span>
  )
}
