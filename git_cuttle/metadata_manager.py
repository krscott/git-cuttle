import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, cast

from git_cuttle.git_ops import canonical_git_dir, default_remote_name, repo_root


SCHEMA_VERSION = 1
WorkspaceKind = Literal["standard", "octopus"]
MigrationFn = Callable[[dict[str, object]], dict[str, object]]


@dataclass(kw_only=True, frozen=True)
class WorkspaceMetadata:
    branch: str
    worktree_path: Path
    tracked_remote: str | None
    kind: WorkspaceKind
    base_ref: str
    octopus_parents: tuple[str, ...]
    created_at: str
    updated_at: str


@dataclass(kw_only=True, frozen=True)
class RepoMetadata:
    git_dir: Path
    repo_root: Path
    default_remote: str | None
    tracked_at: str
    updated_at: str
    workspaces: dict[str, WorkspaceMetadata]


@dataclass(kw_only=True, frozen=True)
class WorkspacesMetadata:
    version: int
    repos: dict[str, RepoMetadata]


def default_metadata_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home) / "gitcuttle" / "workspaces.json"
    return Path.home() / ".local" / "share" / "gitcuttle" / "workspaces.json"


@dataclass(kw_only=True)
class MetadataManager:
    path: Path = field(default_factory=default_metadata_path)

    def ensure_parent_dir(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> WorkspacesMetadata:
        if not self.path.exists():
            return WorkspacesMetadata(version=SCHEMA_VERSION, repos={})

        raw_text = self.path.read_text()
        loaded = json.loads(raw_text)
        loaded, migrated = _migrate_workspaces_metadata(loaded)
        if migrated:
            _write_migration_backup(self.path, raw_text)
            _atomic_write_text(
                self.path,
                json.dumps(loaded, indent=2),
            )

        metadata = _parse_workspaces_metadata(loaded)
        _validate_workspaces_metadata(metadata)
        return metadata

    def write(self, metadata: WorkspacesMetadata) -> None:
        _validate_workspaces_metadata(metadata)
        self.ensure_parent_dir()
        serialized = json.dumps(_serialize_workspaces_metadata(metadata), indent=2)
        _atomic_write_text(self.path, serialized)

    def ensure_repo_tracked(self, *, cwd: Path, now: Callable[[], str] | None = None) -> None:
        tracked_git_dir = canonical_git_dir(cwd)
        tracked_repo_root = repo_root(cwd)

        if tracked_git_dir is None or tracked_repo_root is None:
            raise ValueError("cannot track repository metadata outside a git repository")

        timestamp = (now or _utc_now_iso)()
        metadata = self.read()
        repo_key = str(tracked_git_dir)
        existing_repo = metadata.repos.get(repo_key)

        updated_repo = RepoMetadata(
            git_dir=tracked_git_dir,
            repo_root=tracked_repo_root,
            default_remote=default_remote_name(cwd),
            tracked_at=existing_repo.tracked_at if existing_repo is not None else timestamp,
            updated_at=timestamp,
            workspaces=existing_repo.workspaces if existing_repo is not None else {},
        )

        repos = dict(metadata.repos)
        repos[repo_key] = updated_repo
        self.write(WorkspacesMetadata(version=metadata.version, repos=repos))


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write_text(path: Path, content: str) -> None:
    parent = path.parent
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, path)
        _fsync_directory(parent)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return

    flags = os.O_RDONLY | os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _parse_workspaces_metadata(raw: object) -> WorkspacesMetadata:
    root = _expect_json_object(raw, context="metadata file")

    version = root.get("version")
    repos_raw = root.get("repos")

    if not isinstance(version, int):
        raise ValueError("metadata version must be an integer")
    repos_obj = _expect_json_object(repos_raw, context="metadata repos")

    repos: dict[str, RepoMetadata] = {}
    for repo_key, repo_raw in repos_obj.items():
        repo_obj = _expect_json_object(repo_raw, context="repo records")

        workspaces_raw = repo_obj.get("workspaces")
        workspaces_obj = _expect_json_object(workspaces_raw, context="repo workspaces")

        workspaces: dict[str, WorkspaceMetadata] = {}
        for workspace_key, workspace_raw in workspaces_obj.items():
            workspace_obj = _expect_json_object(
                workspace_raw, context="workspace records"
            )

            octopus_parents_raw = workspace_obj.get("octopus_parents")
            if not isinstance(octopus_parents_raw, list):
                raise ValueError("workspace octopus_parents must be a list of strings")
            octopus_parents: list[str] = []
            for parent_raw in cast(list[object], octopus_parents_raw):
                if not isinstance(parent_raw, str):
                    raise ValueError("workspace octopus_parents must be a list of strings")
                octopus_parents.append(parent_raw)

            kind_raw = workspace_obj.get("kind")
            if kind_raw not in {"standard", "octopus"}:
                raise ValueError("workspace kind must be either 'standard' or 'octopus'")
            kind: WorkspaceKind = (
                "standard" if kind_raw == "standard" else "octopus"
            )

            tracked_remote = workspace_obj.get("tracked_remote")
            if tracked_remote is not None and not isinstance(tracked_remote, str):
                raise ValueError("workspace tracked_remote must be a string or null")

            branch = workspace_obj.get("branch")
            worktree_path = workspace_obj.get("worktree_path")
            base_ref = workspace_obj.get("base_ref")
            created_at = workspace_obj.get("created_at")
            updated_at = workspace_obj.get("updated_at")

            if not isinstance(branch, str):
                raise ValueError("workspace branch must be a string")
            if not isinstance(worktree_path, str):
                raise ValueError("workspace worktree_path must be a string")
            if not isinstance(base_ref, str):
                raise ValueError("workspace base_ref must be a string")
            if not isinstance(created_at, str):
                raise ValueError("workspace created_at must be a string")
            if not isinstance(updated_at, str):
                raise ValueError("workspace updated_at must be a string")

            workspaces[workspace_key] = WorkspaceMetadata(
                branch=branch,
                worktree_path=Path(worktree_path),
                tracked_remote=tracked_remote,
                kind=kind,
                base_ref=base_ref,
                octopus_parents=tuple(octopus_parents),
                created_at=created_at,
                updated_at=updated_at,
            )

        default_remote = repo_obj.get("default_remote")
        if default_remote is not None and not isinstance(default_remote, str):
            raise ValueError("repo default_remote must be a string or null")

        git_dir = repo_obj.get("git_dir")
        repo_root = repo_obj.get("repo_root")
        tracked_at = repo_obj.get("tracked_at")
        updated_at = repo_obj.get("updated_at")

        if not isinstance(git_dir, str):
            raise ValueError("repo git_dir must be a string")
        if not isinstance(repo_root, str):
            raise ValueError("repo repo_root must be a string")
        if not isinstance(tracked_at, str):
            raise ValueError("repo tracked_at must be a string")
        if not isinstance(updated_at, str):
            raise ValueError("repo updated_at must be a string")

        repos[repo_key] = RepoMetadata(
            git_dir=Path(git_dir),
            repo_root=Path(repo_root),
            default_remote=default_remote,
            tracked_at=tracked_at,
            updated_at=updated_at,
            workspaces=workspaces,
        )

    return WorkspacesMetadata(version=version, repos=repos)


def _migrate_workspaces_metadata(raw: object) -> tuple[dict[str, object], bool]:
    root = _expect_json_object(raw, context="metadata file")
    version = root.get("version")

    if not isinstance(version, int):
        raise ValueError("metadata version must be an integer")
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"unsupported metadata schema version: {version}; expected <= {SCHEMA_VERSION}"
        )
    if version == SCHEMA_VERSION:
        return root, False

    migrated = dict(root)
    current_version = version
    while current_version < SCHEMA_VERSION:
        migrate = _MIGRATIONS.get(current_version)
        if migrate is None:
            raise ValueError(
                f"unsupported metadata schema version: {current_version}; expected {SCHEMA_VERSION}"
            )

        migrated = migrate(migrated)
        current_version += 1
        migrated_version = migrated.get("version")
        if migrated_version != current_version:
            raise ValueError(
                f"migration from schema version {current_version - 1} did not produce version {current_version}"
            )

    return migrated, True


def _migrate_v0_to_v1(raw: dict[str, object]) -> dict[str, object]:
    migrated = dict(raw)
    migrated["version"] = 1
    return migrated


_MIGRATIONS: dict[int, MigrationFn] = {
    0: _migrate_v0_to_v1,
}


def _write_migration_backup(path: Path, file_content: str) -> Path:
    timestamp = int(datetime.now(tz=timezone.utc).timestamp())
    backup_path = path.with_name(f"{path.name}.bak.{timestamp}")
    while backup_path.exists():
        timestamp += 1
        backup_path = path.with_name(f"{path.name}.bak.{timestamp}")
    _atomic_write_text(backup_path, file_content)
    return backup_path


def _serialize_workspaces_metadata(metadata: WorkspacesMetadata) -> dict[str, object]:
    repos: dict[str, object] = {}
    for repo_key, repo in metadata.repos.items():
        workspaces: dict[str, object] = {}
        for workspace_key, workspace in repo.workspaces.items():
            workspaces[workspace_key] = {
                "branch": workspace.branch,
                "worktree_path": str(workspace.worktree_path),
                "tracked_remote": workspace.tracked_remote,
                "kind": workspace.kind,
                "base_ref": workspace.base_ref,
                "octopus_parents": list(workspace.octopus_parents),
                "created_at": workspace.created_at,
                "updated_at": workspace.updated_at,
            }

        repos[repo_key] = {
            "git_dir": str(repo.git_dir),
            "repo_root": str(repo.repo_root),
            "default_remote": repo.default_remote,
            "tracked_at": repo.tracked_at,
            "updated_at": repo.updated_at,
            "workspaces": workspaces,
        }

    return {"version": metadata.version, "repos": repos}


def _validate_workspaces_metadata(metadata: WorkspacesMetadata) -> None:
    if metadata.version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported metadata schema version: {metadata.version}; expected {SCHEMA_VERSION}"
        )

    for repo_key, repo in metadata.repos.items():
        if not repo.git_dir.is_absolute():
            raise ValueError("repo.git_dir must be an absolute path")
        canonical_git_dir = repo.git_dir.resolve(strict=False)
        if repo_key != str(canonical_git_dir):
            raise ValueError("repo key must match canonical repo.git_dir realpath")
        if repo.git_dir != canonical_git_dir:
            raise ValueError("repo.git_dir must be stored as canonical realpath")
        if not repo.repo_root.is_absolute():
            raise ValueError("repo.repo_root must be an absolute path")
        _validate_timestamp(repo.tracked_at, field_name="repo.tracked_at")
        _validate_timestamp(repo.updated_at, field_name="repo.updated_at")

        seen_worktree_paths: set[Path] = set()
        for workspace_key, workspace in repo.workspaces.items():
            if workspace_key != workspace.branch:
                raise ValueError("workspace key must match workspace.branch exactly")
            if not workspace.worktree_path.is_absolute():
                raise ValueError("workspace.worktree_path must be an absolute path")
            if workspace.worktree_path in seen_worktree_paths:
                raise ValueError("workspace.worktree_path must be unique within a repo")
            seen_worktree_paths.add(workspace.worktree_path)
            _validate_timestamp(workspace.created_at, field_name="workspace.created_at")
            _validate_timestamp(workspace.updated_at, field_name="workspace.updated_at")
            if workspace.kind == "standard" and workspace.octopus_parents:
                raise ValueError("standard workspaces must not have octopus parents")
            if workspace.kind == "octopus" and len(workspace.octopus_parents) < 2:
                raise ValueError("octopus workspaces must have at least two parents")


def _validate_timestamp(value: str, *, field_name: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc


def _expect_json_object(raw: object, *, context: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError(f"{context} must be an object")
    raw_obj = cast(dict[object, object], raw)
    for key_obj in raw_obj.keys():
        if not isinstance(key_obj, str):
            raise ValueError(f"{context} keys must be strings")
    return cast(dict[str, object], raw_obj)
