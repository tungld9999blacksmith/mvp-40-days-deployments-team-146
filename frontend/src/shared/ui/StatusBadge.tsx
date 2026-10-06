export default function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    completed: { label: 'Hoàn thành', cls: 'text-emerald bg-emerald/10 ring-emerald/20' },
    'due-soon': { label: 'Sắp đến hạn', cls: 'text-warning bg-warning/10 ring-warning/20' },
    overdue: { label: 'Quá hạn', cls: 'text-error bg-error/10 ring-error/20' },
    pending: { label: 'Chờ xử lý', cls: 'text-muted bg-foreground/5 ring-foreground/10' },
  }
  const { label, cls } = map[status] ?? map.pending
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ring-1 ring-inset whitespace-nowrap ${cls}`}>
      <span aria-hidden className="w-1.5 h-1.5 rounded-full bg-current" />
      {label}
    </span>
  )
}
