import { useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { createPayout } from '../api';

function fmt(paise) {
  return (paise / 100).toLocaleString('en-IN', { style: 'currency', currency: 'INR' });
}

export default function PayoutForm({ bankAccounts, availablePaise, onSuccess }) {
  const [amountRupees, setAmountRupees] = useState('');
  const [bankAccountId, setBankAccountId] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setResult(null);

    const paise = Math.round(parseFloat(amountRupees) * 100);
    if (!paise || paise < 100) {
      setError('Minimum payout is ₹1');
      return;
    }
    if (paise > availablePaise) {
      setError(`Insufficient balance. Available: ${fmt(availablePaise)}`);
      return;
    }
    if (!bankAccountId) {
      setError('Please select a bank account');
      return;
    }

    setLoading(true);
    const idempotencyKey = uuidv4();

    try {
      const res = await createPayout(
        {
          amount_paise: paise,
          bank_account_id: bankAccountId,  // UUID string — DO NOT convert to Number()
        },
        idempotencyKey
      );
      setResult({ type: 'success', data: res.data, key: idempotencyKey });
      setAmountRupees('');
      onSuccess?.();
    } catch (err) {
      const msg = err.response?.data?.error || err.response?.data?.detail || 'Request failed';
      setResult({ type: 'error', message: msg });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card p-6">
      <h2 className="text-sm font-mono text-ink-400 uppercase tracking-widest mb-4">Request Payout</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs text-ink-400 mb-1.5 font-mono">Amount (₹)</label>
          <input
            type="number"
            step="0.01"
            min="1"
            value={amountRupees}
            onChange={e => setAmountRupees(e.target.value)}
            placeholder="0.00"
            className="w-full bg-ink-700 border border-ink-600 rounded-lg px-4 py-3 text-white text-lg font-mono focus:outline-none focus:border-brand-500 transition-colors"
          />
          {availablePaise > 0 && (
            <button
              type="button"
              onClick={() => setAmountRupees((availablePaise / 100).toFixed(2))}
              className="mt-1.5 text-xs text-brand-500 hover:text-brand-400 font-mono transition-colors"
            >
              Max: {fmt(availablePaise)}
            </button>
          )}
        </div>

        <div>
          <label className="block text-xs text-ink-400 mb-1.5 font-mono">Bank Account</label>
          <select
            value={bankAccountId}
            onChange={e => setBankAccountId(e.target.value)}
            className="w-full bg-ink-700 border border-ink-600 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-brand-500 transition-colors"
          >
            <option value="">Select bank account</option>
            {bankAccounts?.map(acc => (
              <option key={acc.id} value={acc.id}>
                {acc.account_holder_name} — {acc.masked_account} ({acc.ifsc_code})
              </option>
            ))}
          </select>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-800/50 rounded-lg px-4 py-3 text-red-400 text-sm font-mono">
            {error}
          </div>
        )}

        {result && (
          <div className={`rounded-lg px-4 py-3 text-sm font-mono animate-slide-in ${
            result.type === 'success'
              ? 'bg-green-900/30 border border-green-800/50 text-green-400'
              : 'bg-red-900/30 border border-red-800/50 text-red-400'
          }`}>
            {result.type === 'success' ? (
              <>
                <p className="font-semibold mb-1">✓ Payout queued{result.data.duplicate ? ' (duplicate — idempotent)' : ''}</p>
                <p className="text-xs opacity-70">ID: {result.data.id}</p>
                <p className="text-xs opacity-70">Idempotency Key: {result.key}</p>
              </>
            ) : (
              <p>✗ {result.message}</p>
            )}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-brand-600 hover:bg-brand-500 disabled:bg-ink-700 disabled:text-ink-400 text-white font-semibold py-3 rounded-lg transition-all duration-200 font-mono text-sm"
        >
          {loading ? 'Processing...' : 'Request Payout →'}
        </button>
      </form>
    </div>
  );
}
