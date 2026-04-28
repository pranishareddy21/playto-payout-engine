import uuid
from django.db import models
from django.utils import timezone


class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.email})"

    class Meta:
        db_table = 'merchants'


class BankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='bank_accounts')
    account_number = models.CharField(max_length=20)
    ifsc_code = models.CharField(max_length=11)
    account_holder_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.account_holder_name} - {self.account_number[-4:].rjust(len(self.account_number), '*')}"

    class Meta:
        db_table = 'bank_accounts'


class LedgerEntry(models.Model):
    """
    Immutable ledger. Every money movement is a row.
    Credits = money coming in (customer payments).
    Debits = money going out (payouts, holds).
    
    Balance = SUM(amount_paise WHERE entry_type='credit')
             - SUM(amount_paise WHERE entry_type='debit')
    
    This is always computed at DB level via aggregation — never in Python
    with fetched rows.
    """
    CREDIT = 'credit'
    DEBIT = 'debit'
    ENTRY_TYPE_CHOICES = [
        (CREDIT, 'Credit'),
        (DEBIT, 'Debit'),
    ]

    REFERENCE_TYPES = [
        ('payment', 'Customer Payment'),
        ('payout', 'Payout'),
        ('payout_hold', 'Payout Hold'),
        ('payout_release', 'Payout Release (Failed)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='ledger_entries')
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPE_CHOICES)
    # ALWAYS paise (integer). Never floats. Never Decimal for storage.
    amount_paise = models.BigIntegerField()
    reference_type = models.CharField(max_length=20, choices=REFERENCE_TYPES)
    reference_id = models.UUIDField(null=True, blank=True)
    description = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.entry_type} ₹{self.amount_paise/100:.2f} for {self.merchant.name}"

    class Meta:
        db_table = 'ledger_entries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['merchant', 'created_at']),
            models.Index(fields=['merchant', 'entry_type']),
            models.Index(fields=['reference_id']),
        ]


class Payout(models.Model):
    """
    State machine: pending -> processing -> completed
                                         -> failed
    
    No backwards transitions are allowed. Enforced in save() and the
    update methods. failed->completed is explicitly blocked.
    """
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'

    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PROCESSING, 'Processing'),
        (COMPLETED, 'Completed'),
        (FAILED, 'Failed'),
    ]

    # Legal transitions only
    LEGAL_TRANSITIONS = {
        PENDING: {PROCESSING},
        PROCESSING: {COMPLETED, FAILED},
        COMPLETED: set(),   # terminal
        FAILED: set(),      # terminal
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='payouts')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    attempt_count = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    idempotency_key = models.CharField(max_length=255, db_index=True)
    failure_reason = models.CharField(max_length=500, blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def transition_to(self, new_status):
        """
        Enforces state machine. Raises ValueError on illegal transitions.
        This is the single place where transition validation lives.
        """
        allowed = self.LEGAL_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Illegal payout state transition: {self.status} -> {new_status}. "
                f"Allowed from {self.status}: {allowed or 'none (terminal state)'}"
            )
        self.status = new_status

    def __str__(self):
        return f"Payout {self.id} ₹{self.amount_paise/100:.2f} [{self.status}]"

    class Meta:
        db_table = 'payouts'
        ordering = ['-created_at']
        # Unique constraint: one idempotency key per merchant
        constraints = [
            models.UniqueConstraint(
                fields=['merchant', 'idempotency_key'],
                name='unique_idempotency_key_per_merchant'
            )
        ]
        indexes = [
            models.Index(fields=['merchant', 'status']),
            models.Index(fields=['status', 'processing_started_at']),
        ]


class IdempotencyKey(models.Model):
    """
    Stores idempotency keys with their cached responses.
    Scoped per merchant. Expires after 24 hours.
    
    When a request arrives:
    1. Try INSERT with (merchant, key) — if it succeeds, this is the first request.
    2. If INSERT fails (unique violation), SELECT the cached response.
    3. If the cached response is NULL, the first request is still in-flight — return 409.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE)
    key = models.CharField(max_length=255)
    # Null until the first request completes and stores its response
    response_status_code = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    payout = models.ForeignKey(Payout, on_delete=models.SET_NULL, null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'idempotency_keys'
        constraints = [
            models.UniqueConstraint(
                fields=['merchant', 'key'],
                name='unique_key_per_merchant'
            )
        ]
        indexes = [
            models.Index(fields=['expires_at']),
        ]

    def is_expired(self):
        return timezone.now() > self.expires_at
