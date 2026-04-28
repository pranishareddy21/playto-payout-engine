# EXPLAINER.md — Playto Payout Engine

---

## 1. The Ledger

### Balance calculation query

```python
# payouts/ledger.py — get_balance()
result = LedgerEntry.objects.filter(
    merchant_id=merchant_id
).aggregate(
    total_credits=Sum('amount_paise', filter=Q(entry_type='credit')),
    total_debits=Sum('amount_paise', filter=Q(entry_type='debit')),
)

total_credits = result['total_credits'] or 0
total_debits  = result['total_debits']  or 0
available_paise = total_credits - total_debits
```

This translates to a single SQL:
```sql
SELECT
  COALESCE(SUM(amount_paise) FILTER (WHERE entry_type = 'credit'), 0) AS total_credits,
  COALESCE(SUM(amount_paise) FILTER (WHERE entry_type = 'debit'),  0) AS total_debits
FROM ledger_entries
WHERE merchant_id = %s;
```

### Why this model?

**Append-only ledger, never update money rows.** Every financial event — a customer payment, a payout hold, a fund return — is a new immutable row. Balance is always *derived* from the full history via aggregation, never stored as a mutable field.

This means:
- There is no "balance column" that can get out of sync with history.
- Any discrepancy shows up as an inconsistency between the ledger sum and what was displayed — it cannot be hidden.
- Auditing is free: the entire transaction history is just a SELECT.

**Credits vs debits vs holds:**
- `credit / payment` — customer paid the merchant (money in)
- `debit / payout_hold` — funds held when payout is created (reserved, not yet gone)
- `credit / payout_release` — hold returned when payout fails (atomic with state change)
- `debit / payout` — 0-paise marker when payout completes (hold already covered it)

The invariant we check: `SUM(credits) - SUM(debits) = available_paise >= 0` always.

**Why BigIntegerField, not DecimalField?**  
Paise are integers. Storing as integer eliminates any floating-point representation error. `DecimalField` is correct for *display* math but adds unnecessary precision overhead at storage. Integer paise is the industry standard (Stripe, Razorpay both use integer minor units).

---

## 2. The Lock

### Exact code preventing concurrent overdrafts

```python
# payouts/services.py — create_payout()
with transaction.atomic():
    # SELECT FOR UPDATE acquires a PostgreSQL row-level exclusive lock
    # on this merchant row. Any concurrent transaction issuing the same
    # query will BLOCK at the DB level until we COMMIT or ROLLBACK.
    merchant_locked = Merchant.objects.select_for_update().get(id=merchant_id)

    # Balance computed INSIDE the locked transaction — reads consistent state
    balance = get_balance(merchant_id)
    available = balance['available_paise']

    if available < amount_paise:
        raise InsufficientFundsError(...)

    payout = Payout.objects.create(...)
    debit_merchant(...)   # hold deducted atomically
# COMMIT — lock released here
```

### Database primitive: `SELECT FOR UPDATE`

This is a PostgreSQL row-level exclusive lock (`FOR UPDATE`). When Thread A runs `SELECT ... FOR UPDATE` on merchant row M, PostgreSQL places an exclusive lock. Thread B's identical query blocks at the *database*, not in Python. Thread A checks balance, deducts, commits — lock releases. Thread B unblocks, re-reads the now-reduced balance, and correctly rejects.

**Why not Python-level locking (`threading.Lock`)?**  
Python locks only work within a single process. Celery workers run as multiple separate processes. A `threading.Lock` acquired in worker 1 is invisible to worker 2. Only database-level locks are visible across all connections.

**Why not optimistic locking (version counter)?**  
Optimistic locking detects the conflict *after* the write attempt. You then need retry logic and can still have the conflict window. `SELECT FOR UPDATE` prevents the conflict from forming. For money, pessimistic is safer.

**The concurrency test:**
```python
# Two threads simultaneously attempt 6000 paise payouts on a 10000 paise balance
threads = [threading.Thread(target=attempt_payout) for _ in range(2)]
# Result: exactly 1 success, 1 InsufficientFundsError. No overdraft.
```

---

## 3. The Idempotency

### How the system knows it has seen a key before

We maintain an `IdempotencyKey` table with a `UNIQUE(merchant_id, key)` constraint.

**First request (key not seen):**
1. `IdempotencyKey.objects.get()` → `DoesNotExist` → proceed
2. `IdempotencyKey.objects.create(response_body=None)` — marks key as "in flight"
3. Process payout inside `transaction.atomic()`
4. On commit, update `IdempotencyKey` with `response_body=<serialized response>`, `response_status_code=201`

**Second request (key seen, response ready):**
1. `IdempotencyKey.objects.get()` → found, `response_body` is not null
2. Return the cached `payout`, `response_status_code` immediately — no DB write, no payout created

**Second request (key seen, first still in flight):**
1. `IdempotencyKey.objects.get()` → found, `response_body=None`
2. Return `409 Conflict` — the client knows to wait and retry

**Race between two first-time requests with same key:**  
The `UNIQUE(merchant_id, key)` DB constraint is the guard. Only one `CREATE` wins; the other gets `IntegrityError`, falls back to the `GET` path, and hits the in-flight `409`.

**Key scoping:** `UNIQUE(merchant_id, key)` — the same UUID key from two different merchants creates two independent records. Keys expire after 24 hours (`expires_at` field + TTL check).

---

## 4. The State Machine

### Where failed→completed is blocked

In `Payout.transition_to()`:

```python
# payouts/models.py — Payout

LEGAL_TRANSITIONS = {
    'pending':    {'processing'},
    'processing': {'completed', 'failed'},
    'completed':  set(),   # terminal — no exits
    'failed':     set(),   # terminal — no exits
}

def transition_to(self, new_status):
    allowed = self.LEGAL_TRANSITIONS.get(self.status, set())
    if new_status not in allowed:
        raise ValueError(
            f"Illegal payout state transition: {self.status} -> {new_status}. "
            f"Allowed from {self.status}: {allowed or 'none (terminal state)'}"
        )
    self.status = new_status
```

For `failed → completed`:
- `self.status = 'failed'`
- `allowed = LEGAL_TRANSITIONS['failed'] = set()` (empty — terminal)
- `'completed' not in set()` → `True` → `ValueError` raised

This is the **only** place transitions are validated. All callers (`services.process_payout_transition`, tests, tasks) go through `transition_to()`. There's no way to bypass it without touching this method.

**State change + fund return is atomic:**
```python
# services.py — process_payout_transition()
with transaction.atomic():
    payout = Payout.objects.select_for_update().get(id=payout_id)
    payout.transition_to(Payout.FAILED)        # raises if illegal
    credit_merchant(amount=payout.amount_paise) # returns held funds
    payout.save()
    # Both happen or neither — transaction is atomic
```

---

## 5. The AI Audit

### What AI wrote that was subtly wrong

When I asked an AI assistant to write the balance calculation, it produced:

```python
# ❌ AI-generated — WRONG
def get_balance(merchant_id):
    entries = LedgerEntry.objects.filter(merchant_id=merchant_id)
    balance = 0
    for entry in entries:
        if entry.entry_type == 'credit':
            balance += entry.amount_paise
        else:
            balance -= entry.amount_paise
    return balance
```

**What's wrong:**

1. **Python-level arithmetic on fetched rows.** This pulls *every ledger row* into Python memory and iterates. For a merchant with 10,000 transactions this is a full table scan returned over the wire. At 100,000 rows it becomes a latency problem. More critically, it violates the stated constraint: *"Balance calculations must use database-level operations, not Python arithmetic on fetched rows."*

2. **Race condition window.** Between the `filter()` that fetches rows and the loop that sums them, another transaction can INSERT a new debit. The Python sum is stale before it's even returned. A DB-level `SUM()` aggregation runs inside a single consistent snapshot.

3. **No `select_for_update`** — even if you fix the Python arithmetic, this code outside a transaction gives no guarantee the balance it returns is still valid when you act on it.

**What I replaced it with:**

```python
# ✅ Corrected — DB-level aggregation
result = LedgerEntry.objects.filter(
    merchant_id=merchant_id
).aggregate(
    total_credits=Sum('amount_paise', filter=Q(entry_type='credit')),
    total_debits=Sum('amount_paise', filter=Q(entry_type='debit')),
)
available_paise = (result['total_credits'] or 0) - (result['total_debits'] or 0)
```

This is a single SQL `SELECT SUM(...) FILTER (...)` — atomic, O(1) network round-trip regardless of row count, and consistent within the transaction that calls it.

The AI also initially placed the balance check *outside* the `select_for_update` block:

```python
# ❌ AI-generated — race condition
balance = get_balance(merchant_id)  # read here
if balance >= amount:
    with transaction.atomic():
        Merchant.objects.select_for_update().get(...)  # lock here (too late!)
        # balance might have changed between the check and the lock
```

This is a classic TOCTOU (time-of-check-to-time-of-use) bug. I moved the balance check *inside* the locked transaction so the check and the deduction are protected by the same lock.

---

## Architecture notes

- **No FloatField anywhere.** `BigIntegerField` for all money. Verified by inspecting every model field.
- **Celery beat runs every 30s** to catch stuck payouts. `skip_locked=True` in the beat task prevents multiple workers from double-processing the same stuck payout.
- **Idempotency key expiry** is checked on read, not via a cron. Expired keys are deleted on first encounter and treated as new.
- **The 0-paise "completed" ledger entry** is intentional: it creates an audit trail showing *when* a payout was marked complete, distinct from when the hold was placed.
