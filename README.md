# Playto Payout Engine

A minimal but production-correct payout engine for Playto Pay. Handles merchant ledgers, payout requests with idempotency, concurrency-safe balance deductions, and simulated bank settlement with retry logic.

---

## Live Deployment

Frontend (Vercel):
https://playto-payout-engine-ghtc8e4k7-pranishareddy21s-projects.vercel.app

Backend API (Render):
https://playto-payout-engine-xsix.onrender.com

---

## Stack

* **Backend**: Django 4.2 + DRF + PostgreSQL + Celery + Redis
* **Frontend**: React + Vite + Tailwind CSS
* **Database**: PostgreSQL
* **Deployment**:

  * Backend → Render
  * Frontend → Vercel
  * Database → Render PostgreSQL

---

## Deployment Used

This project was deployed using:

* Backend → Render
* Frontend → Vercel
* Database → PostgreSQL on Render

The application is fully hosted online and works without localhost.

### Deployment Flow

```text
React Frontend (Vercel)
        ↓
Axios API Requests
        ↓
Django REST API (Render)
        ↓
PostgreSQL Database (Render)
        ↓
Merchant + Ledger + BankAccount + Payout Tables
```

Docker configuration exists for local development, but Docker was not used in the final deployment.

---

## What the Project Does

This payout engine allows merchants to:

* View balance
* View ledger entries
* View payout history
* Request payouts
* Select bank accounts
* Track payout status

Money flow:

Customer payment → Merchant credited → Payout request → Balance deducted → Settlement completed or failed → Ledger updated.

---

## Manual Setup (without Docker)

### Prerequisites

* Python 3.11+
* PostgreSQL 14+
* Redis 7+
* Node.js 20+

---

### Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Add PostgreSQL credentials

python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

Run worker:

```bash
celery -A config worker --loglevel=info
```

Run beat scheduler:

```bash
celery -A config beat --loglevel=info
```

---

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on:

```text
http://localhost:5173
```

Backend runs on:

```text
http://localhost:8000
```

---

## API Reference

All requests require:

```text
X-Merchant-Id: <uuid>
```

| Method | Endpoint                 | Description      |
| ------ | ------------------------ | ---------------- |
| GET    | `/api/v1/merchants/`     | List merchants   |
| GET    | `/api/v1/balance/`       | Merchant balance |
| GET    | `/api/v1/ledger/`        | Ledger entries   |
| GET    | `/api/v1/bank-accounts/` | Bank accounts    |
| GET    | `/api/v1/payouts/`       | Payout history   |
| POST   | `/api/v1/payouts/`       | Create payout    |

---

### POST /api/v1/payouts/

Headers:

```text
X-Merchant-Id: <merchant-uuid>
Idempotency-Key: <uuid>
Content-Type: application/json
```

Body:

```json
{
  "amount_paise": 50000,
  "bank_account_id": "<uuid>"
}
```

Responses:

* `201` → Payout created
* `400` → Missing fields
* `401` → Missing merchant header
* `409` → Duplicate idempotency key
* `422` → Insufficient funds

---

## Key Design Decisions

### Money Integrity

All amounts are stored as paise using `BigIntegerField`.

No floating-point values are used.

Balance is calculated using database aggregation.

---

### Concurrency

Uses PostgreSQL row-level locking:

```python
Merchant.objects.select_for_update()
```

This prevents overdraft during simultaneous payout requests.

---

### Idempotency

Each payout request contains an `Idempotency-Key`.

Duplicate requests return the same payout instead of creating a new one.

---

### State Machine

Allowed transitions:

```text
pending → processing → completed
pending → processing → failed
```

Illegal transitions are blocked.

---

### Ledger Model

Ledger is append-only.

Balance is derived using:

```text
credits - debits
```

No balance column is stored.

---

## Running Tests

```bash
cd backend
python manage.py test payouts --verbosity=2
```

Test coverage includes:

* Concurrency protection
* Idempotency
* State machine validation
* Ledger invariant checks

---

## Folder Structure

```text
playto-payout-engine/
├── backend/
│   ├── config/
│   ├── payouts/
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── components/
│   └── api.js
├── docker-compose.yml
├── README.md
└── EXPLAINER.md
```
