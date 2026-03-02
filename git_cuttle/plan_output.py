import json
from dataclasses import dataclass


@dataclass(kw_only=True, frozen=True)
class PlanAction:
    op: str
    target: str
    details: str | None = None


@dataclass(kw_only=True, frozen=True)
class DryRunPlan:
    command: str
    actions: tuple[PlanAction, ...]
    warnings: tuple[str, ...] = ()


def render_human_plan(plan: DryRunPlan) -> str:
    lines: list[str] = [f"Dry-run plan for `{plan.command}`:"]
    if not plan.actions:
        lines.append("No changes planned.")
    else:
        for index, action in enumerate(plan.actions, start=1):
            if action.details is None:
                lines.append(f"{index}. {action.op}: {action.target}")
            else:
                lines.append(f"{index}. {action.op}: {action.target} ({action.details})")

    if plan.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in plan.warnings)

    return "\n".join(lines)


def render_json_plan(plan: DryRunPlan) -> str:
    payload = {
        "command": plan.command,
        "dry_run": True,
        "action_count": len(plan.actions),
        "actions": [
            {
                "op": action.op,
                "target": action.target,
                "details": action.details,
            }
            for action in plan.actions
        ],
        "warnings": list(plan.warnings),
    }
    return json.dumps(payload, indent=2, sort_keys=True)
