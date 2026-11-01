"""Data store selection: Firestore, or the Django database (SQLite locally, PostgreSQL in production)."""
import os

# All of these mean "the Django ORM store" (named "sqlite" internally): the actual database is
# chosen by DATABASE_URL (PostgreSQL) or defaults to the local db.sqlite3 file.
_ORM_ALIASES = {"sqlite", "sql", "orm", "postgres", "postgresql", "database"}


def data_store() -> str:
    """Return 'sqlite' (Django database) or 'firestore' (default)."""
    value = (os.environ.get("DATA_STORE") or "firestore").strip().lower()
    return "sqlite" if value in _ORM_ALIASES else value


def use_sqlite() -> bool:
    return data_store() == "sqlite"


def use_firestore() -> bool:
    return not use_sqlite()
