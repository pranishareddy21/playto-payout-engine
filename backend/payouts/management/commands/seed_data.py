"""
Seed script: populates 3 merchants with credit history and bank accounts.
Run: python manage.py seed_data
"""
import uuid
from django.core.management.base import BaseCommand
from django.db import transaction
from payouts.models import Merchant, BankAccount
from payouts.ledger import credit_merchant


MERCHANTS = [
    {
        'name': 'PixelCraft Studio',
        'email': 'billing@pixelcraft.in',
        'bank': {
            'account_number': '50100234567890',
            'ifsc_code': 'HDFC0001234',
            'account_holder_name': 'PixelCraft Studio Pvt Ltd',
        },
        'credits': [
            (250000, 'Client A - Logo design project - INV-001'),
            (180000, 'Client B - Website redesign milestone 1 - INV-002'),
            (420000, 'Client C - Brand identity package - INV-003'),
            (95000,  'Client D - Social media kit - INV-004'),
        ]
    },
    {
        'name': 'Growthly Marketing',
        'email': 'finance@growthly.io',
        'bank': {
            'account_number': '60200345678901',
            'ifsc_code': 'ICIC0005678',
            'account_holder_name': 'Growthly Marketing LLP',
        },
        'credits': [
            (500000, 'Retainer - TechCorp US - March 2026 - INV-101'),
            (320000, 'Campaign management - StartupXYZ - INV-102'),
            (150000, 'SEO audit - GlobalInc - INV-103'),
            (780000, 'Annual contract payment Q1 - BigBrand - INV-104'),
        ]
    },
    {
        'name': 'Nilesh Freelance Dev',
        'email': 'nilesh@devcraft.me',
        'bank': {
            'account_number': '40100456789012',
            'ifsc_code': 'SBIN0009012',
            'account_holder_name': 'Nilesh Kumar',
        },
        'credits': [
            (300000, 'React app - US client - Milestone 1 - INV-201'),
            (300000, 'React app - US client - Milestone 2 - INV-202'),
            (120000, 'Bug fixing & maintenance - INV-203'),
            (450000, 'Full-stack SaaS MVP - European startup - INV-204'),
        ]
    },
]


class Command(BaseCommand):
    help = 'Seed database with test merchants, bank accounts, and credit history'

    def handle(self, *args, **options):
        self.stdout.write('Seeding database...')

        with transaction.atomic():
            for m_data in MERCHANTS:
                merchant, created = Merchant.objects.get_or_create(
                    email=m_data['email'],
                    defaults={'name': m_data['name']}
                )
                action = 'Created' if created else 'Already exists'
                self.stdout.write(f"  {action}: {merchant.name}")

                # Bank account
                bank, _ = BankAccount.objects.get_or_create(
                    merchant=merchant,
                    account_number=m_data['bank']['account_number'],
                    defaults={
                        'ifsc_code': m_data['bank']['ifsc_code'],
                        'account_holder_name': m_data['bank']['account_holder_name'],
                    }
                )

                # Credits (only if new merchant)
                if created:
                    for amount_paise, description in m_data['credits']:
                        credit_merchant(
                            merchant=merchant,
                            amount_paise=amount_paise,
                            reference_type='payment',
                            reference_id=uuid.uuid4(),
                            description=description,
                        )
                    self.stdout.write(f"    Added {len(m_data['credits'])} credit entries")

        self.stdout.write(self.style.SUCCESS('\nSeed complete! Merchants:'))
        for m in Merchant.objects.all():
            from payouts.ledger import get_balance
            bal = get_balance(str(m.id))
            rupees = bal['available_paise'] / 100
            self.stdout.write(f"  {m.name} | ID: {m.id} | Balance: ₹{rupees:.2f}")
