from django.conf import settings

if settings.DATA_STORE == "sqlite":
    from .sqlite import ConsumptionFS
else:
    from expenses.firestore_models import ConsumptionFS

__all__ = ["ConsumptionFS"]
