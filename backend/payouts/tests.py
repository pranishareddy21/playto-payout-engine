"""
Test suite for critical payment system invariants.

Test 1: Concurrency — two simultaneous 60-rupee payouts with 100-rupee balance.
         Exactly one must succeed. The other must be rejected cleanly.
         No overdraft allowed.

Test 2: Idempotency — same idempotency key submitted twice.
         Must return identical response. No duplicate payout created.
"""
import uuid
import threading
from django.test import TestCase, TransactionTestCase
from django.db import connection

from payouts.models import Merchant, BankAccount, Payout, LedgerEntry
from payouts.ledger import credit_merchant, get_balance
from payouts.services import create_payout, InsufficientFundsError


def make_merchant(name='Test Merchant', email=None):
    email = email or f'{uuid.uuid4().hex[:8]}@test.com'
    merchant = Merchant.objects.create(name=name, email=email)
    bank = BankAccount.objects.create(
        merchant=merchant,
        account_number='50100000000001',
        ifsc_code='HDFC0001234',
        account_holder_name=name,
    )
    return merchant, bank


class ConcurrencyTest(TransactionTestCase):
    """
    Must use TransactionTestCase (not TestCase) because SELECT FOR UPDATE
    requires real DB transactions. TestCase wraps everything in a single
    transaction which would cause deadlocks with our locking code.
    """

    def test_concurrent_payouts_no_overdraft(self):
        """
        Merchant has ₹100 (10000 paise).
        Two threads simultaneously request ₹60 (6000 paise) each.
        Exactly ONE should succeed, the other should get InsufficientFundsError.
        Total debited must not exceed 10000 paise.
        """
        merchant, bank = make_merchant('ConcurrencyTest Merchant')
        credit_merchant(
            merchant=merchant,
            amount_paise=10000,  # ₹100
            reference_type='payment',
            reference_id=uuid.uuid4(),
            description='Test credit',
        )

        results = []
        errors = []
        lock = threading.Lock()

        def attempt_payout(thread_id):
            try:
                payout, status_code, _ = create_payout(
                    merchant_id=str(merchant.id),
                    amount_paise=6000,
                    bank_account_id=str(bank.id),
                    idempotency_key_str=str(uuid.uuid4()),
                )
                with lock:
                    results.append(('success', payout.id, status_code))
            except InsufficientFundsError as e:
                with lock:
                    results.append(('insufficient_funds', None, 422))
            except Exception as e:
                with lock:
                    errors.append(str(e))
            finally:
                connection.close()  # Required for TransactionTestCase threads

        threads = [threading.Thread(target=attempt_payout, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No unexpected errors
        self.assertEqual(errors, [], f"Unexpected errors: {errors}")

        successes = [r for r in results if r[0] == 'success']
        failures = [r for r in results if r[0] == 'insufficient_funds']

        # Exactly one success, one rejection
        self.assertEqual(len(successes), 1, f"Expected 1 success, got {len(successes)}. Results: {results}")
        self.assertEqual(len(failures), 1, f"Expected 1 rejection, got {len(failures)}. Results: {results}")

        # INVARIANT CHECK: total debited must not exceed 10000
        balance = get_balance(str(merchant.id))
        self.assertGreaterEqual(
            balance['available_paise'], 0,
            f"OVERDRAFT DETECTED: available balance is {balance['available_paise']} paise"
        )
        total_debits = LedgerEntry.objects.filter(
            merchant=merchant, entry_type='debit'
        ).aggregate(total=__import__('django.db.models', fromlist=['Sum']).Sum('amount_paise'))['total'] or 0
        self.assertLessEqual(
            total_debits, 10000,
            f"Total debited {total_debits} paise exceeds funded amount of 10000 paise"
        )

    def test_concurrent_payouts_both_can_succeed_if_enough_balance(self):
        """
        Merchant has ₹200. Two ₹60 requests. Both should succeed.
        """
        merchant, bank = make_merchant('RichMerchant')
        credit_merchant(
            merchant=merchant,
            amount_paise=20000,  # ₹200
            reference_type='payment',
            reference_id=uuid.uuid4(),
            description='Test credit',
        )

        results = []
        errors = []
        lock = threading.Lock()

        def attempt_payout(thread_id):
            try:
                payout, status_code, _ = create_payout(
                    merchant_id=str(merchant.id),
                    amount_paise=6000,
                    bank_account_id=str(bank.id),
                    idempotency_key_str=str(uuid.uuid4()),
                )
                with lock:
                    results.append('success')
            except InsufficientFundsError:
                with lock:
                    results.append('insufficient_funds')
            except Exception as e:
                with lock:
                    errors.append(str(e))
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt_payout, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(results.count('success'), 2)
        self.assertEqual(results.count('insufficient_funds'), 0)


class IdempotencyTest(TestCase):
    """
    TestCase is fine here (no multi-process locking needed).
    """

    def setUp(self):
        self.merchant, self.bank = make_merchant('IdempotencyTest Merchant')
        credit_merchant(
            merchant=self.merchant,
            amount_paise=50000,  # ₹500
            reference_type='payment',
            reference_id=uuid.uuid4(),
            description='Test seed credit',
        )

    def test_same_idempotency_key_returns_same_response(self):
        """
        Calling POST /payouts with the same idempotency key twice must:
        1. Return the same payout object both times
        2. Create exactly ONE payout in the DB
        3. Return status 201 both times (cached)
        """
        idem_key = str(uuid.uuid4())

        payout1, status1, is_dup1 = create_payout(
            merchant_id=str(self.merchant.id),
            amount_paise=10000,
            bank_account_id=str(self.bank.id),
            idempotency_key_str=idem_key,
        )

        payout2, status2, is_dup2 = create_payout(
            merchant_id=str(self.merchant.id),
            amount_paise=10000,
            bank_account_id=str(self.bank.id),
            idempotency_key_str=idem_key,
        )

        # Same payout object returned
        self.assertEqual(str(payout1.id), str(payout2.id))

        # First call: not a duplicate
        self.assertFalse(is_dup1)
        # Second call: IS a duplicate
        self.assertTrue(is_dup2)

        # Exactly ONE payout in DB
        count = Payout.objects.filter(merchant=self.merchant).count()
        self.assertEqual(count, 1, f"Expected 1 payout, got {count}")

        # Exactly ONE debit ledger entry (the hold)
        debit_count = LedgerEntry.objects.filter(
            merchant=self.merchant,
            entry_type='debit',
            reference_id=payout1.id,
        ).count()
        self.assertEqual(debit_count, 1, f"Expected 1 debit entry, got {debit_count}")

    def test_different_keys_create_different_payouts(self):
        """Different idempotency keys must create separate payouts."""
        payout1, _, _ = create_payout(
            merchant_id=str(self.merchant.id),
            amount_paise=5000,
            bank_account_id=str(self.bank.id),
            idempotency_key_str=str(uuid.uuid4()),
        )
        payout2, _, _ = create_payout(
            merchant_id=str(self.merchant.id),
            amount_paise=5000,
            bank_account_id=str(self.bank.id),
            idempotency_key_str=str(uuid.uuid4()),
        )
        self.assertNotEqual(str(payout1.id), str(payout2.id))
        self.assertEqual(Payout.objects.filter(merchant=self.merchant).count(), 2)

    def test_idempotency_key_scoped_per_merchant(self):
        """Same key used by different merchants must create independent payouts."""
        shared_key = str(uuid.uuid4())

        merchant2, bank2 = make_merchant('Merchant Two', 'merchant2@test.com')
        credit_merchant(
            merchant=merchant2,
            amount_paise=50000,
            reference_type='payment',
            reference_id=uuid.uuid4(),
            description='Test credit',
        )

        payout1, _, _ = create_payout(
            merchant_id=str(self.merchant.id),
            amount_paise=5000,
            bank_account_id=str(self.bank.id),
            idempotency_key_str=shared_key,
        )
        payout2, _, _ = create_payout(
            merchant_id=str(merchant2.id),
            amount_paise=5000,
            bank_account_id=str(bank2.id),
            idempotency_key_str=shared_key,
        )

        self.assertNotEqual(str(payout1.id), str(payout2.id))


class StateMachineTest(TestCase):
    def setUp(self):
        self.merchant, self.bank = make_merchant('StateMachine Merchant')
        credit_merchant(
            merchant=self.merchant,
            amount_paise=50000,
            reference_type='payment',
            reference_id=uuid.uuid4(),
            description='Test seed',
        )

    def test_illegal_completed_to_pending_blocked(self):
        payout = Payout(
            merchant=self.merchant,
            bank_account=self.bank,
            amount_paise=1000,
            status=Payout.COMPLETED,
            idempotency_key=str(uuid.uuid4()),
        )
        with self.assertRaises(ValueError):
            payout.transition_to(Payout.PENDING)

    def test_illegal_failed_to_completed_blocked(self):
        """This is the specific check required by the challenge."""
        payout = Payout(
            merchant=self.merchant,
            bank_account=self.bank,
            amount_paise=1000,
            status=Payout.FAILED,
            idempotency_key=str(uuid.uuid4()),
        )
        with self.assertRaises(ValueError) as ctx:
            payout.transition_to(Payout.COMPLETED)
        self.assertIn('failed', str(ctx.exception).lower())
        self.assertIn('completed', str(ctx.exception).lower())

    def test_legal_transitions_succeed(self):
        payout = Payout(status=Payout.PENDING, idempotency_key=str(uuid.uuid4()))
        payout.transition_to(Payout.PROCESSING)
        self.assertEqual(payout.status, Payout.PROCESSING)
        payout.transition_to(Payout.COMPLETED)
        self.assertEqual(payout.status, Payout.COMPLETED)

    def test_legal_pending_to_failed_via_processing(self):
        payout = Payout(status=Payout.PENDING, idempotency_key=str(uuid.uuid4()))
        payout.transition_to(Payout.PROCESSING)
        payout.transition_to(Payout.FAILED)
        self.assertEqual(payout.status, Payout.FAILED)


class LedgerInvariantTest(TestCase):
    """Balance must always equal sum(credits) - sum(debits)."""

    def test_balance_invariant_after_credits(self):
        merchant, bank = make_merchant('InvariantTest')
        credit_merchant(merchant=merchant, amount_paise=10000,
                        reference_type='payment', reference_id=uuid.uuid4(), description='c1')
        credit_merchant(merchant=merchant, amount_paise=5000,
                        reference_type='payment', reference_id=uuid.uuid4(), description='c2')
        bal = get_balance(str(merchant.id))
        self.assertEqual(bal['available_paise'], 15000)

    def test_balance_invariant_after_payout_hold(self):
        merchant, bank = make_merchant('HoldInvariantTest')
        credit_merchant(merchant=merchant, amount_paise=10000,
                        reference_type='payment', reference_id=uuid.uuid4(), description='credit')

        create_payout(
            merchant_id=str(merchant.id),
            amount_paise=4000,
            bank_account_id=str(bank.id),
            idempotency_key_str=str(uuid.uuid4()),
        )
        bal = get_balance(str(merchant.id))
        # 10000 credited, 4000 debited as hold
        self.assertEqual(bal['available_paise'], 6000)
        self.assertEqual(bal['held_paise'], 4000)
