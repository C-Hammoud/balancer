from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import DjangoConsumption
from firebase_client import get_firestore_client
from firebase_admin import firestore
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

@receiver(post_save, sender=DjangoConsumption)
def sync_consumption_to_firestore(sender, instance, **kwargs):
    try:
        db = get_firestore_client()
        if db:
            db.collection("consumptions").document(str(instance.pk)).set(instance.to_dict())
    except Exception as e:
        logger.exception("Failed to sync consumption %s to Firestore: %s", instance.pk, e)

@receiver(post_delete, sender=DjangoConsumption)
def delete_consumption_from_firestore(sender, instance, **kwargs):
    try:
        db = get_firestore_client()
        if db:
            db.collection("consumptions").document(str(instance.pk)).delete()
    except Exception as e:
        logger.exception("Failed to delete consumption %s from Firestore: %s", instance.pk, e)

@receiver(post_save, sender=User)
def sync_user_to_firestore(sender, instance, created, **kwargs):
    try:
        db = get_firestore_client()
    except FileNotFoundError:
        logger.exception("Firebase service account key not found; skipping user sync")
        return
    try:
        uid = str(instance.pk)
        doc_ref = db.collection("users").document(uid)
        payload = {
            "uid": uid,
            "username": instance.username,
            "email": instance.email,
            "first_name": instance.first_name,
            "last_name": instance.last_name,
            "is_active": instance.is_active,
            "is_staff": instance.is_staff,
            "last_login": firestore.SERVER_TIMESTAMP if instance.last_login else None,
        }
        if created:
            doc_ref.set({**payload, "created_at": firestore.SERVER_TIMESTAMP})
        else:
            update_payload = {k: v for k, v in payload.items() if v is not None}
            doc_ref.set(update_payload, merge=True)
    except Exception:
        logger.exception("Failed to sync user %s to Firestore", getattr(instance, "pk", "<unknown>"))