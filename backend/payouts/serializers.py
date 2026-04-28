from rest_framework import serializers
from .models import Merchant, BankAccount, LedgerEntry, Payout


class BankAccountSerializer(serializers.ModelSerializer):
    masked_account = serializers.SerializerMethodField()

    class Meta:
        model = BankAccount
        fields = ['id', 'account_holder_name', 'ifsc_code', 'masked_account', 'is_active', 'created_at']

    def get_masked_account(self, obj):
        n = obj.account_number
        return '*' * (len(n) - 4) + n[-4:]


class LedgerEntrySerializer(serializers.ModelSerializer):
    amount_rupees = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = ['id', 'entry_type', 'amount_paise', 'amount_rupees',
                  'reference_type', 'reference_id', 'description', 'created_at']

    def get_amount_rupees(self, obj):
        return obj.amount_paise / 100


class PayoutSerializer(serializers.ModelSerializer):
    amount_rupees = serializers.SerializerMethodField()
    bank_account = BankAccountSerializer(read_only=True)

    class Meta:
        model = Payout
        fields = ['id', 'amount_paise', 'amount_rupees', 'status', 'bank_account',
                  'attempt_count', 'failure_reason', 'idempotency_key',
                  'processing_started_at', 'created_at', 'updated_at']

    def get_amount_rupees(self, obj):
        return obj.amount_paise / 100


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ['id', 'name', 'email', 'created_at']


class CreatePayoutSerializer(serializers.Serializer):
    amount_paise = serializers.IntegerField(min_value=100)  # min ₹1
    bank_account_id = serializers.UUIDField()

    def validate_amount_paise(self, value):
        if value <= 0:
            raise serializers.ValidationError("amount_paise must be positive")
        return value
