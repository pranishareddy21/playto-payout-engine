export default function StatusBadge({ status }) {
  const classes = {
    pending: 'badge-pending',
    processing: 'badge-processing',
    completed: 'badge-completed',
    failed: 'badge-failed',
  };
  const dots = {
    pending: 'bg-yellow-400',
    processing: 'bg-blue-400 animate-pulse',
    completed: 'bg-green-400',
    failed: 'bg-red-400',
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium border ${classes[status] || 'bg-ink-700 text-ink-400 border-ink-600'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dots[status] || 'bg-ink-400'}`} />
      {status}
    </span>
  );
}
