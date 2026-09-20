import json
from typing import Any, Optional

from src.authz import Principal
from src.db import AuditLog


def _serialize_details(details: Optional[dict[str, Any]]) -> Optional[str]:
    if not details:
        return None
    return json.dumps(details, ensure_ascii=False, sort_keys=True, default=str)


def record_audit_event(
    session,
    *,
    principal: Principal,
    action: str,
    object_type: str,
    object_id: Optional[str] = None,
    vendor_id: Optional[int] = None,
    outcome: str = "success",
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    event = AuditLog(
        actor_subject=principal.subject,
        actor_name=principal.display_name,
        actor_email=principal.email,
        actor_role=principal.role,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        vendor_id=vendor_id,
        outcome=outcome,
        details_json=_serialize_details(details),
    )
    session.add(event)
    session.flush()
    return event
