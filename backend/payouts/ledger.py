"""
Ledger service. All balance calculations happen HERE, at DB level.

The invariant: available_balance + held_balance == total_credits - total_completed_debits

- credits: customer payments (always positive entries)
- debit/payout_hold: funds held when a payout is created (pending/processing)
- debit/payout: funds gone when payout completes
- credit/payout_release: funds returned when payout fails (cancels the hold)

So:
  available_balance = SUM(credits) - SUM(debits)
  held_balance = SUM of active holds (pending/processing payout amounts)
"""
from django.db import models as django_models
from django.db.models import Sum, Q
from .models import LedgerEntry, Merchant


def get_balance(merchant_id):
    """
    Compute merchant balances using a single DB aggregation query.
    Returns dict with available_paise and held_paise.
    
    This uses DB-level SUM, never Python arithmetic on fetched rows.
    """
    result = LedgerEntry.objects.filter(
        merchant_id=merchant_id
    ).aggregate(
        total_credits=Sum(
            'amount_paise',
            filter=Q(entry_type='credit')
        ),
        total_debits=Sum(
            'amount_paise',
            filter=Q(entry_type='debit')
        ),
    )

    total_credits = result['total_credits'] or 0
    total_debits = result['total_debits'] or 0
    available_paise = total_credits - total_debits

    # Held = sum of pending/processing payout amounts (the holds we deducted)
    from .models import Payout
    held_result = Payout.objects.filter(
        merchant_id=merchant_id,
        status__in=['pending', 'processing']
    ).aggregate(held=Sum('amount_paise'))
    held_paise = held_result['held'] or 0

    return {
        'available_paise': available_paise,
        'held_paise': held_paise,
        'total_credits_paise': total_credits,
        'total_debits_paise': total_debits,
    }


def credit_merchant(merchant, amount_paise, reference_type, reference_id, description):
    """Add a credit entry to the ledger (money coming in)."""
    return LedgerEntry.objects.create(
        merchant=merchant,
        entry_type=LedgerEntry.CREDIT,
        amount_paise=amount_paise,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )


def debit_merchant(merchant, amount_paise, reference_type, reference_id, description):
    """Add a debit entry to the ledger (money going out / being held)."""
    return LedgerEntry.objects.create(
        merchant=merchant,
        entry_type=LedgerEntry.DEBIT,
        amount_paise=amount_paise,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )
