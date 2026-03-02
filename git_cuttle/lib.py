from dataclasses import dataclass


@dataclass(kw_only=True, frozen=True)
class Options:
    branch: str | None = None
    base_ref: str | None = None
    parent_refs: tuple[str, ...] = ()
    destination: bool = False
    dry_run: bool = False
    json_output: bool = False
    force: bool = False
    interactive: bool = False
    target_parent: str | None = None
