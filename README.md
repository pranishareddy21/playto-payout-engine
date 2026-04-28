# Playto Payout Engine

A minimal but production-correct payout engine for Playto Pay. Handles merchant ledgers, payout requests with idempotency, concurrency-safe balance deductions, and simulated bank settlement with retry logic.

## Stack

- **Backend**: Django 4.2 + DRF + PostgreSQL + Celery + Redis
- **Frontend**: React + Vite + Tailwind CSS
- **Workers**: Celery worker (payout processing) + Celery Beat (retry stuck payouts every 30s)

---

## Quick Start with Docker

```bash
git clone <repo-url>
cd playto-payout
docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api/v1/
- Django Admin: http://localhost:8000/admin/

Seed data is loaded automatically on first run.

---

## Manual Setup (without Docker)

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Node.js 20+

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your DB credentials

# Database setup
createdb playto_payout
python manage.py migrate

# Seed merchants
python manage.py seed_data

# Start Django
python manage.py runserver

# In a separate terminal — Celery worker
celery -A config worker --loglevel=info

# In another terminal — Celery beat (retry scheduler)
celery -A config beat --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
# Set VITE_API_URL=http://localhost:8000/api/v1
npm run dev
```

---

## API Reference

All requests require `X-Merchant-Id: <uuid>` header.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/merchants/` | List all merchants |
| GET | `/api/v1/merchants/<id>/` | Merchant detail + balance |
| GET | `/api/v1/balance/` | Current merchant balance |
| GET | `/api/v1/ledger/` | Recent ledger entries |
| GET | `/api/v1/bank-accounts/` | Merchant bank accounts |
| GET | `/api/v1/payouts/` | Payout history |
| POST | `/api/v1/payouts/` | Create payout request |
| GET | `/api/v1/payouts/<id>/` | Payout detail |

### POST /api/v1/payouts/

**Headers:**
```
X-Merchant-Id: <merchant-uuid>
Idempotency-Key: <client-generated-uuid>
Content-Type: application/json
```

**Body:**
```json
{
  "amount_paise": 50000,
  "bank_account_id": "<bank-account-uuid>"
}
```

**Responses:**
- `201` — Payout created and queued
- `400` — Missing/invalid fields
- `401` — Missing merchant header
- `409` — Idempotency key in flight (retry after brief delay)
- `422` — Insufficient funds

---

## Running Tests

```bash
cd backend
python manage.py test payouts --verbosity=2
```

Key tests:
- **`ConcurrencyTest.test_concurrent_payouts_no_overdraft`** — Two threads race to overdraw. Exactly one wins.
- **`IdempotencyTest.test_same_idempotency_key_returns_same_response`** — Duplicate key returns same payout, no duplicate created.
- **`StateMachineTest.test_illegal_failed_to_completed_blocked`** — Illegal transition raises ValueError.
- **`LedgerInvariantTest`** — Balance invariant holds after credits and holds.

---

## Key Design Decisions

### Money integrity
All amounts stored as `BigIntegerField` in paise (integer). No floats anywhere. Balance calculated via DB-level `SUM()` aggregation, never Python loops over fetched rows.

### Concurrency
`SELECT FOR UPDATE` on the merchant row inside `transaction.atomic()`. This is a PostgreSQL row-level exclusive lock — works across all Celery worker processes, unlike Python threading locks.

### Idempotency
`UNIQUE(merchant_id, key)` DB constraint as the guard. `response_body=NULL` signals "in-flight" and returns 409. Completed responses are cached and replayed. Keys expire after 24 hours.

### State machine
`Payout.transition_to()` is the single validation point. `LEGAL_TRANSITIONS` dict defines allowed moves. Terminal states (`completed`, `failed`) have empty sets — nothing can follow them. Failed→completed raises `ValueError`.

### Fund return atomicity
When a payout fails, the credit entry (fund return) and status update happen inside the same `transaction.atomic()`. Either both commit or neither does. No partial states.

---

## Project Structure

```
playto-payout/
├── backend/
│   ├── config/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── celery.py
│   ├── payouts/
│   │   ├── models.py        # Merchant, BankAccount, LedgerEntry, Payout, IdempotencyKey
│   │   ├── ledger.py        # Balance calculation (DB aggregation)
│   │   ├── services.py      # create_payout() with SELECT FOR UPDATE
│   │   ├── tasks.py         # Celery: process_payout, retry_stuck_payouts
│   │   ├── views.py         # DRF API views
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   └── management/commands/seed_data.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main dashboard with polling
│   │   ├── api.js           # Axios client
│   │   └── components/
│   │       ├── BalanceCard.jsx
│   │       ├── PayoutForm.jsx
│   │       ├── PayoutTable.jsx
│   │       ├── LedgerTable.jsx
│   │       ├── StatusBadge.jsx
│   │       └── MerchantSelector.jsx
│   └── Dockerfile
├── docker-compose.yml
├── README.md
└── EXPLAINER.md
```
