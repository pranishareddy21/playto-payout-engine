export default function MerchantSelector({ merchants, selectedId, onSelect }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-mono text-ink-400 uppercase tracking-widest">Merchant</span>
      <select
        value={selectedId || ''}
        onChange={e => onSelect(e.target.value)}
        className="bg-ink-700 border border-ink-600 rounded-lg px-3 py-1.5 text-sm text-white font-mono focus:outline-none focus:border-brand-500 transition-colors"
      >
        <option value="">Select merchant…</option>
        {merchants?.map(m => (
          <option key={m.id} value={m.id}>{m.name}</option>
        ))}
      </select>
    </div>
  );
}
