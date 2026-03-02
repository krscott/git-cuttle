import pathlib
import subprocess

from git_cuttle.git_ops import in_progress_operation


def _init_repo(path: pathlib.Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], check=True, cwd=path)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True, cwd=path)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        check=True,
        cwd=path,
    )
    (path / "README.md").write_text("repo\n")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=path)
    subprocess.run(["git", "commit", "-m", "init"], check=True, cwd=path)


def test_in_progress_operation_returns_none_when_repo_is_clean(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    assert in_progress_operation(repo) is None


def test_in_progress_operation_detects_git_state_marker(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    git_dir_result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    )
    git_dir = pathlib.Path(git_dir_result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (repo / git_dir).resolve(strict=False)

    (git_dir / "MERGE_HEAD").write_text("abc123\n")

    assert in_progress_operation(repo) == "MERGE_HEAD"
