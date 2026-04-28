from django.urls import path
from . import views

urlpatterns = [
    path('merchants/', views.MerchantListView.as_view()),
    path('merchants/<uuid:merchant_id>/', views.MerchantDetailView.as_view()),
    path('balance/', views.BalanceView.as_view()),
    path('ledger/', views.LedgerView.as_view()),
    path('bank-accounts/', views.BankAccountListView.as_view()),
    path('payouts/', views.PayoutListView.as_view()),
    path('payouts/<uuid:payout_id>/', views.PayoutDetailView.as_view()),
    path('diagnostic/', views.DiagnosticView.as_view()),
    path('process-payouts/', views.ProcessPendingPayoutsView.as_view()),
]
