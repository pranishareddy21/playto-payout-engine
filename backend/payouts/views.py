import uuid
import logging
from django.db.models import Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Merchant, BankAccount, LedgerEntry, Payout
from .serializers import (
    MerchantSerializer, BankAccountSerializer,
    LedgerEntrySerializer, PayoutSerializer, CreatePayoutSerializer
)
from .ledger import get_balance
from .services import create_payout, InsufficientFundsError
from .tasks import process_payout

logger = logging.getLogger(__name__)


def get_merchant(request):
    """Simple merchant auth via X-Merchant-Id header."""
    merchant_id = request.headers.get('X-Merchant-Id')
    if not merchant_id:
        return None
    try:
        return Merchant.objects.get(id=merchant_id)
    except (Merchant.DoesNotExist, ValueError):
        return None


class MerchantListView(APIView):
    def get(self, request):
        merchants = Merchant.objects.all()
        return Response(MerchantSerializer(merchants, many=True).data)


class MerchantDetailView(APIView):
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=404)
        
        balance = get_balance(merchant_id)
        data = MerchantSerializer(merchant).data
        data['balance'] = balance
        return Response(data)


class BalanceView(APIView):
    def get(self, request):
        merchant = get_merchant(request)
        if not merchant:
            return Response({'error': 'X-Merchant-Id header required'}, status=401)
        
        balance = get_balance(str(merchant.id))
        return Response({
            'merchant_id': str(merchant.id),
            'merchant_name': merchant.name,
            **balance
        })


class LedgerView(APIView):
    def get(self, request):
        merchant = get_merchant(request)
        if not merchant:
            return Response({'error': 'X-Merchant-Id header required'}, status=401)
        
        entries = LedgerEntry.objects.filter(merchant=merchant).order_by('-created_at')[:50]
        return Response(LedgerEntrySerializer(entries, many=True).data)


class BankAccountListView(APIView):
    def get(self, request):
        merchant = get_merchant(request)
        if not merchant:
            return Response({'error': 'X-Merchant-Id header required'}, status=401)
        
        accounts = BankAccount.objects.filter(merchant=merchant, is_active=True)
        return Response(BankAccountSerializer(accounts, many=True).data)


class PayoutListView(APIView):
    def get(self, request):
        merchant = get_merchant(request)
        if not merchant:
            return Response({'error': 'X-Merchant-Id header required'}, status=401)
        
        payouts = Payout.objects.filter(merchant=merchant).select_related('bank_account').order_by('-created_at')[:50]
        return Response(PayoutSerializer(payouts, many=True).data)

    def post(self, request):
        merchant = get_merchant(request)
        if not merchant:
            return Response({'error': 'X-Merchant-Id header required'}, status=401)

        # Validate idempotency key
        idempotency_key_str = request.headers.get('Idempotency-Key')
        if not idempotency_key_str:
            return Response({'error': 'Idempotency-Key header is required'}, status=400)

        # Validate UUID format
        try:
            uuid.UUID(idempotency_key_str)
        except ValueError:
            return Response({'error': 'Idempotency-Key must be a valid UUID'}, status=400)

        # Validate request body
        serializer = CreatePayoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=400)

        try:
            payout, status_code, was_duplicate = create_payout(
                merchant_id=str(merchant.id),
                amount_paise=serializer.validated_data['amount_paise'],
                bank_account_id=str(serializer.validated_data['bank_account_id']),
                idempotency_key_str=idempotency_key_str,
            )
        except InsufficientFundsError as e:
            return Response({'error': str(e)}, status=422)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=404)
        except BankAccount.DoesNotExist:
            return Response({'error': 'Bank account not found or inactive'}, status=404)
        except Exception as e:
            logger.exception(f"Unexpected error creating payout: {e}")
            return Response({'error': 'Internal server error'}, status=500)

        if status_code == 409:
            return Response({'error': 'Request with this idempotency key is already in flight'}, status=409)

        if payout is None:
            return Response({'error': 'Failed to create payout'}, status=500)

        # Enqueue background processing
        if not was_duplicate:
            process_payout.delay(str(payout.id))

        response_data = PayoutSerializer(payout).data
        response_data['duplicate'] = was_duplicate
        return Response(response_data, status=status_code)


class PayoutDetailView(APIView):
    def get(self, request, payout_id):
        merchant = get_merchant(request)
        if not merchant:
            return Response({'error': 'X-Merchant-Id header required'}, status=401)
        
        try:
            payout = Payout.objects.select_related('bank_account').get(
                id=payout_id, merchant=merchant
            )
        except Payout.DoesNotExist:
            return Response({'error': 'Payout not found'}, status=404)
        
        return Response(PayoutSerializer(payout).data)
