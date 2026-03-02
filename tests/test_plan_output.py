import json

from git_cuttle.plan_output import DryRunPlan, PlanAction, render_human_plan, render_json_plan


def test_render_human_plan_lists_actions_and_warnings() -> None:
    plan = DryRunPlan(
        command="prune",
        actions=(
            PlanAction(op="delete-worktree", target="feature/login"),
            PlanAction(
                op="delete-branch",
                target="feature/login",
                details="merged-pr",
            ),
        ),
        warnings=("workspace has unpushed commits",),
    )

    rendered = render_human_plan(plan)

    assert rendered == (
        "Dry-run plan for `prune`:\n"
        "1. delete-worktree: feature/login\n"
        "2. delete-branch: feature/login (merged-pr)\n"
        "Warnings:\n"
        "- workspace has unpushed commits"
    )


def test_render_human_plan_handles_empty_action_set() -> None:
    plan = DryRunPlan(command="delete", actions=())

    rendered = render_human_plan(plan)

    assert rendered == "Dry-run plan for `delete`:\nNo changes planned."


def test_render_json_plan_returns_machine_readable_payload() -> None:
    plan = DryRunPlan(
        command="delete",
        actions=(
            PlanAction(op="delete-worktree", target="feature/a"),
            PlanAction(op="delete-branch", target="feature/a", details="forced"),
        ),
        warnings=("branch has no upstream",),
    )

    rendered = render_json_plan(plan)
    parsed = json.loads(rendered)

    assert parsed == {
        "action_count": 2,
        "actions": [
            {
                "details": None,
                "op": "delete-worktree",
                "target": "feature/a",
            },
            {
                "details": "forced",
                "op": "delete-branch",
                "target": "feature/a",
            },
        ],
        "command": "delete",
        "dry_run": True,
        "warnings": ["branch has no upstream"],
    }
