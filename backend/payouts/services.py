"""
Payout service. Contains the critical transactional logic.

The concurrency problem:
  Merchant has 100 INR (10000 paise). Two requests for 60 INR arrive simultaneously.
  Without locking:
    Thread A reads balance: 10000 ✓ >= 6000
    Thread B reads balance: 10000 ✓ >= 6000
    Thread A deducts: balance = 4000
    Thread B deducts: balance = -2000  ← OVERDRAFT BUG
  
  With SELECT FOR UPDATE:
    Thread A: SELECT ... FOR UPDATE (acquires row lock)
    Thread B: SELECT ... FOR UPDATE (BLOCKS, waiting for A)
    Thread A checks: 10000 >= 6000, deducts, COMMITS, releases lock
    Thread B resumes: 4000 < 6000, REJECTS cleanly
    
The lock is a PostgreSQL row-level lock. It blocks at DB level,
not Python level. Python threading locks would not help across
multiple processes/workers.
"""
import uuid
import json
import logging
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta

from .models import Merchant, Payout, LedgerEntry, IdempotencyKey, BankAccount
from .ledger import credit_merchant, debit_merchant, get_balance

logger = logging.getLogger(__name__)


class InsufficientFundsError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


def create_payout(merchant_id, amount_paise, bank_account_id, idempotency_key_str):
    """
    Create a payout with full idempotency and concurrency safety.
    
    Returns: (payout, status_code, was_duplicate)
    """
    merchant = Merchant.objects.get(id=merchant_id)

    # --- IDEMPOTENCY CHECK ---
    # We try to get-or-create the idempotency key record.
    # get_or_create is NOT atomic enough here — we need the DB unique constraint
    # to be our guard. We use select_for_update to handle the in-flight case.
    from django.conf import settings
    expires_at = timezone.now() + timedelta(seconds=settings.IDEMPOTENCY_KEY_TTL)

    # First: check if key already exists (expired keys are cleaned out separately)
    try:
        idem_key = IdempotencyKey.objects.get(
            merchant=merchant,
            key=idempotency_key_str
        )
        if idem_key.is_expired():
            # Expired key — treat as new
            idem_key.delete()
            raise IdempotencyKey.DoesNotExist
        
        # Key exists. Is the response ready?
        if idem_key.response_body is None:
            # First request is still in flight — return 409 Conflict
            return None, 409, True
        
        # Return the cached response
        return idem_key.payout, idem_key.response_status_code, True

    except IdempotencyKey.DoesNotExist:
        pass

    # Create the idempotency key record (response_body=None = in flight)
    # The DB unique constraint prevents duplicates; if two requests race here,
    # one gets IntegrityError and must retry the GET path.
    try:
        idem_record = IdempotencyKey.objects.create(
            merchant=merchant,
            key=idempotency_key_str,
            expires_at=expires_at,
        )
    except Exception:
        # Lost the race — another thread already created it
        try:
            idem_record = IdempotencyKey.objects.get(merchant=merchant, key=idempotency_key_str)
            if idem_record.response_body is None:
                return None, 409, True
            return idem_record.payout, idem_record.response_status_code, True
        except IdempotencyKey.DoesNotExist:
            raise

    # --- CRITICAL SECTION: balance check + hold with SELECT FOR UPDATE ---
    try:
        with transaction.atomic():
            # SELECT FOR UPDATE acquires a row-level lock on this merchant row.
            # Any concurrent transaction trying to do the same will BLOCK here
            # until we commit or rollback. This is the ONLY correct way to prevent
            # concurrent overdrafts — Python-level locks don't work across processes.
            merchant_locked = Merchant.objects.select_for_update().get(id=merchant_id)

            # Compute balance INSIDE the locked transaction
            balance = get_balance(merchant_id)
            available = balance['available_paise']

            if available < amount_paise:
                # Release the idempotency key so the client can retry with different amount
                idem_record.delete()
                raise InsufficientFundsError(
                    f"Insufficient funds: available {available} paise, requested {amount_paise} paise"
                )

            bank_account = BankAccount.objects.get(
                id=bank_account_id,
                merchant=merchant_locked,
                is_active=True
            )

            # Create the payout record
            payout = Payout.objects.create(
                merchant=merchant_locked,
                bank_account=bank_account,
                amount_paise=amount_paise,
                status=Payout.PENDING,
                idempotency_key=idempotency_key_str,
            )

            # Debit (hold) the funds immediately — this reduces available balance
            debit_merchant(
                merchant=merchant_locked,
                amount_paise=amount_paise,
                reference_type='payout_hold',
                reference_id=payout.id,
                description=f'Hold for payout {payout.id}',
            )

        # Transaction committed. Update idempotency record with response.
        idem_record.payout = payout
        idem_record.response_status_code = 201
        idem_record.response_body = {'payout_id': str(payout.id)}
        idem_record.save()

        return payout, 201, False

    except (InsufficientFundsError, BankAccount.DoesNotExist):
        raise
    except Exception as e:
        # Unexpected error — delete idempotency key so client can retry
        idem_record.delete()
        raise


def process_payout_transition(payout_id, new_status, failure_reason=''):
    """
    Move a payout to a new status. For failed payouts, atomically returns funds.
    
    The failed->completed block: transition_to() raises ValueError.
    The funds return is ATOMIC with the state change — both in one transaction.
    """
    with transaction.atomic():
        # Lock the payout row to prevent concurrent state changes
        payout = Payout.objects.select_for_update().get(id=payout_id)

        # This raises ValueError for illegal transitions (e.g., failed->completed)
        payout.transition_to(new_status)

        if new_status == Payout.PROCESSING:
            payout.processing_started_at = timezone.now()
            payout.attempt_count += 1

        elif new_status == Payout.COMPLETED:
            # Replace the hold debit with a final payout debit
            # The hold was already deducted, so we just record the final entry
            debit_merchant(
                merchant=payout.merchant,
                amount_paise=0,  # hold already covers this
                reference_type='payout',
                reference_id=payout.id,
                description=f'Payout completed {payout.id}',
            )

        elif new_status == Payout.FAILED:
            payout.failure_reason = failure_reason
            # ATOMIC: return held funds in the SAME transaction as state change
            # If this transaction rolls back, the funds don't return AND status doesn't change.
            credit_merchant(
                merchant=payout.merchant,
                amount_paise=payout.amount_paise,
                reference_type='payout_release',
                reference_id=payout.id,
                description=f'Funds returned: payout {payout.id} failed - {failure_reason}',
            )

        payout.save()
        return payout
