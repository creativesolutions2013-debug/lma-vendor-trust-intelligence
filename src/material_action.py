from dataclasses import dataclass


@dataclass(frozen=True)
class MaterialActionPlan:
    action: str
    create_assessment: bool
    assessment_type: str | None
    requires_rationale: bool
    close_event: bool


def plan_material_action(
    action: str,
) -> MaterialActionPlan:
    value = (action or "").strip()

    if value == "Monitor":
        return MaterialActionPlan(
            action=value,
            create_assessment=False,
            assessment_type=None,
            requires_rationale=False,
            close_event=False,
        )

    if value == "Request Evidence":
        return MaterialActionPlan(
            action=value,
            create_assessment=False,
            assessment_type=None,
            requires_rationale=False,
            close_event=False,
        )

    if value == "Targeted Review":
        return MaterialActionPlan(
            action=value,
            create_assessment=True,
            assessment_type="Targeted Material Change Review",
            requires_rationale=False,
            close_event=False,
        )

    if value == "Full Reassessment":
        return MaterialActionPlan(
            action=value,
            create_assessment=True,
            assessment_type="Full Material Change Reassessment",
            requires_rationale=True,
            close_event=False,
        )

    if value == "Escalate":
        return MaterialActionPlan(
            action=value,
            create_assessment=False,
            assessment_type=None,
            requires_rationale=True,
            close_event=False,
        )

    if value == "Dismiss":
        return MaterialActionPlan(
            action=value,
            create_assessment=False,
            assessment_type=None,
            requires_rationale=True,
            close_event=True,
        )

    raise ValueError(
        f"Unsupported analyst action: {action}"
    )
