import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({ baseURL: BASE_URL });

// Attach merchant ID to every request
api.interceptors.request.use(config => {
  const merchantId = localStorage.getItem('merchantId');
  if (merchantId) config.headers['X-Merchant-Id'] = merchantId;
  return config;
});

export const getMerchants = () => api.get('/merchants/');
export const getMerchant = (id) => api.get(`/merchants/${id}/`);
export const getBalance = () => api.get('/balance/');
export const getLedger = () => api.get('/ledger/');
export const getBankAccounts = () => api.get('/bank-accounts/');
export const getPayouts = () => api.get('/payouts/');
export const getPayout = (id) => api.get(`/payouts/${id}/`);

export const createPayout = (data, idempotencyKey) =>
  api.post('/payouts/', data, {
    headers: { 'Idempotency-Key': idempotencyKey },
  });

export default api;

export const processPendingPayouts = () => api.post('/process-payouts/');
