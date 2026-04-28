# Playto Payout Engine

Cross-border payout infrastructure for Indian merchants. Built for the Playto Pay founding engineer challenge.

**Live Demo:** https://playto-payout-engine-ghtc8e4k7-pranishareddy21s-projects.vercel.app
**API:** https://playto-payout-engine-xsix.onrender.com

---

## What it does

This project allows merchants to:

* View available balance
* View ledger history
* View payouts
* Request payouts to linked bank accounts
* Track payout status in real time

Money flow:

Customer payment → Merchant balance credited → Merchant requests payout → Funds deducted → Payout succeeds or fails → Ledger updates automatically.

---

## Tech Stack

| Layer      | Tech                           |
| ---------- | ------------------------------ |
| Backend    | Django + Django REST Framework |
| Database   | PostgreSQL                     |
| Queue      | Celery + Redis                 |
| Frontend   | React + Vite + Tailwind CSS    |
| Deployment | Render + Vercel                |

---

## Architecture

```text
React Frontend (Vercel)
        ↓
Axios API Requests
        ↓
Django REST API (Render)
        ↓
PostgreSQL Database
        ↓
Ledger + Merchant + BankAccount + Payout tables
```

---

## Features

* Merchant dashboard
* Real-time balance updates
* Ledger history tracking
* Bank account selection
* Payout creation
* Idempotency support
* PostgreSQL row locking
* Polling every 4 seconds for live updates

---

## API Endpoints

### Merchants

GET /api/v1/merchants/

### Balance

GET /api/v1/balance/

### Ledger

GET /api/v1/ledger/

### Bank Accounts

GET /api/v1/bank-accounts/

### Payouts

GET /api/v1/payouts/
POST /api/v1/payouts/

---

## Local Setup

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on:
http://localhost:5173

Backend runs on:
http://localhost:8000

---

## Deployment

### Backend

https://playto-payout-engine-xsix.onrender.com

### Frontend

https://playto-payout-engine-ghtc8e4k7-pranishareddy21s-projects.vercel.app

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
├── README.md
├── EXPLAINER.md
└── docker-compose.yml
```
