import os
from pathlib import Path
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore, storage
from typing import Optional

_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(_BASE_DIR / ".env")


def resolve_firebase_key_path() -> str:
    """
    Resolve Firebase service account JSON path.
    Uses FIREBASE_KEY_PATH from env when the file exists; otherwise tries project-root fallbacks
    (so local dev works when .env still has a production absolute path).
    """
    env_path = (os.environ.get("FIREBASE_KEY_PATH") or "").strip()
    candidates = []
    if env_path:
        p = Path(env_path)
        candidates.append(p if p.is_absolute() else _BASE_DIR / env_path)
    candidates.extend([
        _BASE_DIR / "finance-tracker-firebase_key.json",
        _BASE_DIR / "resources" / "finance-tracker-firebase_key.json",
    ])
    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            if path.is_file():
                return str(path.resolve())
        except OSError:
            continue
    return str(candidates[0]) if candidates else str(_BASE_DIR / "resources" / "finance-tracker-firebase_key.json")


FIREBASE_KEY_PATH = resolve_firebase_key_path()
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID")
FIREBASE_STORAGE_BUCKET = os.environ.get("FIREBASE_STORAGE_BUCKET")


def get_firestore_client():
    from django.conf import settings
    if getattr(settings, "DATA_STORE", "firestore") == "sqlite":
        raise RuntimeError(
            "Firestore is disabled (DATA_STORE=sqlite). Use Django ORM via budgeting.store."
        )
    if not firebase_admin._apps:
        if not os.path.isfile(FIREBASE_KEY_PATH):
            raise RuntimeError(
                f"Firebase key not found at {FIREBASE_KEY_PATH}. "
                "Set DATA_STORE=sqlite in .env for local development without Firebase."
            )
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def get_storage_bucket():
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
    return storage.bucket()
