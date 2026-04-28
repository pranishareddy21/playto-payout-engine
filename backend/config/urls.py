from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def home(request):
    return JsonResponse({"status": "Playto payout engine running"})

urlpatterns = [
    path('', home),
    path('admin/', admin.site.urls),
    path('api/v1/', include('payouts.urls')),
]