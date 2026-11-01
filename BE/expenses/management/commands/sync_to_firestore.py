from django.core.management.base import BaseCommand
from expenses.models import DjangoConsumption
from expenses.firestore_models import ConsumptionFS

class Command(BaseCommand):
    help = 'Migrate Consumption data from Django ORM to Firestore'

    def handle(self, *args, **kwargs):
        for item in DjangoConsumption.objects.all():
            inst = ConsumptionFS(
                pk=str(item.pk),
                date=item.date,
                amount=item.amount,
                currency=item.currency,
                amount_usd=item.amount_usd,
                consumption_type=item.consumption_type,
                note=item.note,
                created_by=str(item.created_by_id) if item.created_by_id else None,
                created_at=item.created_at,
                modified_by=str(item.modified_by_id) if item.modified_by_id else None,
                modified_at=item.modified_at,
                record_status=item.record_status
            )
            inst.save()
            self.stdout.write(self.style.SUCCESS(f'Migrated Consumption {item.pk}'))