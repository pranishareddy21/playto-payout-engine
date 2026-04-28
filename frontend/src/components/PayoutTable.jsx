import StatusBadge from './StatusBadge';

function fmt(paise) {
  return (paise / 100).toLocaleString('en-IN', { style: 'currency', currency: 'INR' });
}

function timeAgo(dateStr) {
  const diff = (Date.now() - new Date(dateStr)) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(dateStr).toLocaleDateString('en-IN');
}

export default function PayoutTable({ payouts, loading }) {
  if (loading && !payouts?.length) return (
    <div className="card p-6 space-y-3">
      {[1,2,3].map(i => (
        <div key={i} className="h-12 bg-ink-700 rounded animate-pulse" />
      ))}
    </div>
  );

  return (
    <div className="card overflow-hidden">
      <div className="px-6 py-4 border-b border-ink-700 flex items-center justify-between">
        <h2 className="text-sm font-mono text-ink-400 uppercase tracking-widest">Payout History</h2>
        <span className="text-xs font-mono text-ink-500">{payouts?.length || 0} records</span>
      </div>
      {!payouts?.length ? (
        <div className="px-6 py-12 text-center text-ink-400 text-sm font-mono">No payouts yet</div>
      ) : (
        <div className="divide-y divide-ink-700/50">
          {payouts.map(p => (
            <div key={p.id} className="px-6 py-4 flex items-center justify-between gap-4 hover:bg-ink-700/30 transition-colors animate-fade-in">
              <div className="flex items-center gap-3 min-w-0">
                <StatusBadge status={p.status} />
                <div className="min-w-0">
                  <p className="text-sm font-mono text-white truncate">{fmt(p.amount_paise)}</p>
                  <p className="text-xs text-ink-400 font-mono truncate">
                    {p.bank_account?.masked_account} · {p.bank_account?.ifsc_code}
                  </p>
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-xs font-mono text-ink-400">{timeAgo(p.created_at)}</p>
                {p.failure_reason && (
                  <p className="text-xs text-red-400 font-mono mt-0.5 max-w-[160px] truncate" title={p.failure_reason}>
                    {p.failure_reason}
                  </p>
                )}
                {p.attempt_count > 1 && (
                  <p className="text-xs text-yellow-500 font-mono">attempt {p.attempt_count}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
