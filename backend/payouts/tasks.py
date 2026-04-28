"""
Celery background tasks for payout processing.

Simulates bank settlement:
  - 70% success
  - 20% failure  
  - 10% hang (stuck in processing, will be retried)

Retry logic:
  - Payouts stuck in processing > 30 seconds are retried
  - Exponential backoff: 30s, 60s, 120s
  - Max 3 attempts, then fail and return funds
"""
import random
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.db import transaction

from .models import Payout
from .services import process_payout_transition

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_payout(self, payout_id):
    """
    Process a single payout. Simulates bank API call.
    Moves pending -> processing -> completed/failed.
    """
    try:
        payout = Payout.objects.get(id=payout_id)
    except Payout.DoesNotExist:
        logger.error(f"Payout {payout_id} not found")
        return

    if payout.status != Payout.PENDING:
        logger.info(f"Payout {payout_id} not in pending state (current: {payout.status}), skipping")
        return

    # Move to processing
    try:
        payout = process_payout_transition(payout_id, Payout.PROCESSING)
    except ValueError as e:
        logger.error(f"Invalid transition for {payout_id}: {e}")
        return

    # Simulate bank settlement with probability distribution
    # 70% succeed, 20% fail, 10% hang (simulate timeout)
    outcome = random.random()

    if outcome < 0.70:
        # SUCCESS
        try:
            process_payout_transition(payout_id, Payout.COMPLETED)
            logger.info(f"Payout {payout_id} completed successfully")
        except ValueError as e:
            logger.error(f"Failed to complete payout {payout_id}: {e}")

    elif outcome < 0.90:
        # FAILURE
        reasons = [
            "Bank account not found",
            "IFSC validation failed",
            "Beneficiary account frozen",
            "Daily transaction limit exceeded",
            "Invalid account number",
        ]
        reason = random.choice(reasons)
        try:
            process_payout_transition(payout_id, Payout.FAILED, failure_reason=reason)
            logger.info(f"Payout {payout_id} failed: {reason}")
        except ValueError as e:
            logger.error(f"Failed to fail payout {payout_id}: {e}")

    else:
        # HANG — 10% simulate a stuck payout, intentionally not transitioning
        # The retry_stuck_payouts beat task will pick this up after 30 seconds
        logger.info(f"Payout {payout_id} is hanging in processing (simulated timeout)")


@shared_task
def retry_stuck_payouts():
    """
    Celery Beat task: runs every 30 seconds.
    Finds payouts stuck in processing > 30 seconds and retries or fails them.
    
    Retry schedule (exponential backoff approximated by attempt count):
      Attempt 1: stuck > 30s  -> retry
      Attempt 2: stuck > 60s  -> retry
      Attempt 3: stuck > 120s -> fail permanently
    """
    now = timezone.now()

    # Find stuck payouts
    stuck_payouts = Payout.objects.filter(
        status=Payout.PROCESSING,
        processing_started_at__isnull=False,
        processing_started_at__lt=now - timedelta(seconds=30)
    ).select_for_update(skip_locked=True)  # skip_locked: don't block on locked rows

    with transaction.atomic():
        for payout in stuck_payouts:
            attempt = payout.attempt_count
            stuck_seconds = (now - payout.processing_started_at).total_seconds()

            # Check backoff thresholds
            required_wait = 30 * (2 ** (attempt - 1))  # 30, 60, 120
            if stuck_seconds < required_wait:
                continue

            if attempt >= payout.max_attempts:
                # Max retries exhausted — fail and return funds
                logger.warning(f"Payout {payout.id} exceeded max retries ({attempt}), failing")
                try:
                    process_payout_transition(
                        str(payout.id),
                        Payout.FAILED,
                        failure_reason=f"Max retries exceeded after {attempt} attempts"
                    )
                except ValueError as e:
                    logger.error(f"Could not fail payout {payout.id}: {e}")
            else:
                # Retry: reset to pending and re-queue
                logger.info(f"Retrying payout {payout.id} (attempt {attempt})")
                try:
                    with transaction.atomic():
                        payout_obj = Payout.objects.select_for_update().get(id=payout.id)
                        # Manual reset for retry — we allow processing->pending only in retry path
                        payout_obj.status = Payout.PENDING
                        payout_obj.processing_started_at = None
                        payout_obj.save()
                    process_payout.delay(str(payout.id))
                except Exception as e:
                    logger.error(f"Failed to retry payout {payout.id}: {e}")
