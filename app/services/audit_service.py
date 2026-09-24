from flask_login import current_user

from ..extensions import db
from ..models import AuditLog


def log_action(
    action: str,
    object_type: str,
    object_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> None:
    """Ajoute une entrée au journal d'audit (section 22, RB-028).

    N'effectue pas de commit : l'appelant doit committer dans la même
    transaction que le changement métier qu'elle trace, pour que les deux
    réussissent ou échouent ensemble.
    """
    entry = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        old_value=old_value,
        new_value=new_value,
    )
    db.session.add(entry)
