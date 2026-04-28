import { useState, useEffect, useCallback } from 'react';
import { getMerchants, getBalance, getLedger, getBankAccounts, getPayouts } from './api';
import BalanceCard from './components/BalanceCard';
import PayoutForm from './components/PayoutForm';
import PayoutTable from './components/PayoutTable';
import LedgerTable from './components/LedgerTable';
import MerchantSelector from './components/MerchantSelector';

const POLL_INTERVAL = 4000; // 4 seconds for live status updates

export default function App() {
  const [merchants, setMerchants] = useState([]);
  const [selectedMerchantId, setSelectedMerchantId] = useState(() =>
    localStorage.getItem('merchantId') || ''
  );
  const [balance, setBalance] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [payouts, setPayouts] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [loadingData, setLoadingData] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('payouts');

  // Load merchants on mount
  useEffect(() => {
    getMerchants()
      .then(r => {
        setMerchants(r.data);
        if (!selectedMerchantId && r.data.length > 0) {
          selectMerchant(r.data[0].id);
        }
      })
      .catch(() => setError('Cannot reach API. Is the backend running?'));
  }, []);

  function selectMerchant(id) {
    setSelectedMerchantId(id);
    localStorage.setItem('merchantId', id);
    setBalance(null);
    setLedger([]);
    setPayouts([]);
    setBankAccounts([]);
  }

  const fetchDashboard = useCallback(async () => {
    if (!selectedMerchantId) return;
    try {
      const [balRes, ledgerRes, payoutsRes, bankRes] = await Promise.all([
        getBalance(),
        getLedger(),
        getPayouts(),
        getBankAccounts(),
      ]);
      setBalance(balRes.data);
      setLedger(ledgerRes.data);
      setPayouts(payoutsRes.data);
      setBankAccounts(bankRes.data);
      setError('');
    } catch (e) {
      setError('Failed to fetch data. Check backend connection.');
    }
  }, [selectedMerchantId]);

  // Initial load + poll for live updates
  useEffect(() => {
    if (!selectedMerchantId) return;
    setLoadingData(true);
    fetchDashboard().finally(() => setLoadingData(false));

    const interval = setInterval(fetchDashboard, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchDashboard, selectedMerchantId]);

  // Check if any payout is in a live state (pending/processing)
  const hasLivePayouts = payouts.some(p => ['pending', 'processing'].includes(p.status));

  return (
    <div className="min-h-screen bg-ink-900">
      {/* Header */}
      <header className="border-b border-ink-700 bg-ink-800/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-brand-600 flex items-center justify-center">
              <svg width="16" height="16" fill="none" viewBox="0 0 24 24">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div>
              <span className="font-semibold text-white text-sm">Playto</span>
              <span className="text-ink-400 text-sm"> / Payout Engine</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {hasLivePayouts && (
              <div className="flex items-center gap-1.5 text-xs font-mono text-blue-400">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                Live
              </div>
            )}
            <MerchantSelector
              merchants={merchants}
              selectedId={selectedMerchantId}
              onSelect={selectMerchant}
            />
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 bg-red-900/30 border border-red-800/50 rounded-xl px-5 py-4 text-red-400 text-sm font-mono">
            ⚠ {error}
          </div>
        )}

        {!selectedMerchantId ? (
          <div className="text-center py-24">
            <p className="text-ink-400 font-mono text-sm">Select a merchant to view dashboard</p>
          </div>
        ) : (
          <div className="space-y-6 animate-fade-in">
            {/* Balance + Payout Form row */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
              <div className="lg:col-span-3">
                <BalanceCard balance={balance} />
              </div>
              <div className="lg:col-span-2">
                <PayoutForm
                  key={selectedMerchantId}
                  bankAccounts={bankAccounts}
                  availablePaise={balance?.available_paise || 0}
                  onSuccess={fetchDashboard}
                />
              </div>
            </div>

            {/* Tab switcher */}
            <div className="flex gap-1 bg-ink-800 border border-ink-700 rounded-xl p-1 w-fit">
              {['payouts', 'ledger'].map(tab => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2 rounded-lg text-xs font-mono font-medium transition-all ${
                    activeTab === tab
                      ? 'bg-ink-600 text-white'
                      : 'text-ink-400 hover:text-white'
                  }`}
                >
                  {tab === 'payouts' ? `Payouts (${payouts.length})` : `Ledger (${ledger.length})`}
                </button>
              ))}
            </div>

            {/* Data tables */}
            {activeTab === 'payouts' ? (
              <PayoutTable payouts={payouts} loading={loadingData} />
            ) : (
              <LedgerTable entries={ledger} loading={loadingData} />
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="max-w-6xl mx-auto px-6 py-6 mt-8 border-t border-ink-800">
        <p className="text-xs font-mono text-ink-600 text-center">
          Playto Payout Engine · Amounts in paise · Polling every {POLL_INTERVAL/1000}s
        </p>
      </footer>
    </div>
  );
}
