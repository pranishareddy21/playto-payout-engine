function fmt(paise) {
  return (paise / 100).toLocaleString('en-IN', { style: 'currency', currency: 'INR' });
}

export default function BalanceCard({ balance, merchantName }) {
  if (!balance) return (
    <div className="card p-6 animate-pulse">
      <div className="h-4 bg-ink-700 rounded w-1/3 mb-4" />
      <div className="h-10 bg-ink-700 rounded w-2/3" />
    </div>
  );

  return (
    <div className="card p-6 animate-fade-in">
      <p className="text-xs font-mono text-ink-400 uppercase tracking-widest mb-1">Available Balance</p>
      <p className="text-4xl font-bold text-white mb-4 tracking-tight">
        {fmt(balance.available_paise)}
      </p>
      <div className="flex gap-4 pt-4 border-t border-ink-700">
        <div>
          <p className="text-xs text-ink-400 font-mono mb-0.5">Held</p>
          <p className="text-sm font-semibold text-yellow-400">{fmt(balance.held_paise)}</p>
        </div>
        <div>
          <p className="text-xs text-ink-400 font-mono mb-0.5">Total Received</p>
          <p className="text-sm font-semibold text-brand-500">{fmt(balance.total_credits_paise)}</p>
        </div>
        <div>
          <p className="text-xs text-ink-400 font-mono mb-0.5">Total Paid Out</p>
          <p className="text-sm font-semibold text-red-400">{fmt(balance.total_debits_paise)}</p>
        </div>
      </div>
    </div>
  );
}
