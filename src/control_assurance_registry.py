"""Case-driven UI registration; no allowed-domain list or evaluator prerequisite."""
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from src.control_assurance import ControlCase


class ReviewCaseIdentity(Protocol):
    case_id: str
    title: str


@dataclass(frozen=True)
class ReviewFamily:
    name: str
    cases: tuple[ReviewCaseIdentity, ...]
    renderer: Callable[..., None] | None = None  # compatibility adapters only
    state_keys: tuple[str, ...] = ("m3d_current_review",)


def registered_review_families(cases: Iterable[ControlCase], *, adapters: Iterable[ReviewFamily] = ()):
    """Any additional applicable case appears without changing the common UI."""
    registrations = {}
    for adapter in adapters:
        if not adapter.cases:
            continue
        if not isinstance(adapter.name, str) or not adapter.name.strip():
            raise ValueError("A review adapter requires a family label.")
        if adapter.name in registrations:
            raise ValueError("Duplicate review adapters cannot silently replace applicable cases.")
        if len({c.case_id for c in adapter.cases}) != len(adapter.cases):
            raise ValueError("Case IDs must be unique within each registered family.")
        registrations[adapter.name] = adapter
    grouped = {}
    for case in cases:
        if not isinstance(case.family, str) or not case.family.strip():
            raise ValueError("An applicable review case requires a family label.")
        grouped.setdefault(case.family, []).append(case)
    for name, items in grouped.items():
        if name in registrations:
            raise ValueError("A family cannot mix a compatibility adapter with common review cases.")
        if len({c.case_id for c in items}) != len(items):
            raise ValueError("Case IDs must be unique within each registered family.")
        registrations[name] = ReviewFamily(name, tuple(items))
    return registrations
