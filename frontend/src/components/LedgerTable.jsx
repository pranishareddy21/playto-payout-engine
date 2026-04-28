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

const REF_LABELS = {
  payment: { label: 'Payment', color: 'text-brand-500' },
  payout_hold: { label: 'Hold', color: 'text-yellow-400' },
  payout: { label: 'Payout', color: 'text-red-400' },
  payout_release: { label: 'Returned', color: 'text-blue-400' },
};

export default function LedgerTable({ entries, loading }) {
  if (loading && !entries?.length) return (
    <div className="card p-6 space-y-3">
      {[1,2,3,4].map(i => (
        <div key={i} className="h-10 bg-ink-700 rounded animate-pulse" />
      ))}
    </div>
  );

  return (
    <div className="card overflow-hidden">
      <div className="px-6 py-4 border-b border-ink-700 flex items-center justify-between">
        <h2 className="text-sm font-mono text-ink-400 uppercase tracking-widest">Ledger</h2>
        <span className="text-xs font-mono text-ink-500">{entries?.length || 0} entries</span>
      </div>
      {!entries?.length ? (
        <div className="px-6 py-12 text-center text-ink-400 text-sm font-mono">No ledger entries</div>
      ) : (
        <div className="divide-y divide-ink-700/50">
          {entries.map(e => {
            const isCredit = e.entry_type === 'credit';
            const ref = REF_LABELS[e.reference_type] || { label: e.reference_type, color: 'text-ink-400' };
            return (
              <div key={e.id} className="px-6 py-3 flex items-center justify-between gap-4 hover:bg-ink-700/30 transition-colors">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className={`text-xs font-mono font-semibold ${ref.color}`}>{ref.label}</span>
                    <span className="text-xs text-ink-500 font-mono truncate max-w-xs">{e.description}</span>
                  </div>
                  <p className="text-xs text-ink-500 font-mono">{timeAgo(e.created_at)}</p>
                </div>
                <span className={`text-sm font-mono font-semibold flex-shrink-0 ${isCredit ? 'text-brand-500' : 'text-red-400'}`}>
                  {isCredit ? '+' : '-'}{fmt(e.amount_paise)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
