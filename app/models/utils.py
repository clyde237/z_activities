from datetime import datetime, timezone


def utc_now() -> datetime:
    """Retourne l'horodatage courant en UTC timezone-aware."""
    return datetime.now(timezone.utc)
