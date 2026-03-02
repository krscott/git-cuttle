import os
import subprocess
from pathlib import Path

import pytest


def _git(
    *, cwd: Path, args: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=check,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _init_repo(path: Path) -> None:
    _git(cwd=path, args=["init", "-b", "main"])
    _git(cwd=path, args=["config", "user.name", "Test User"])
    _git(cwd=path, args=["config", "user.email", "test@example.com"])
    (path / "README.md").write_text("repo\n")
    _git(cwd=path, args=["add", "README.md"])
    _git(cwd=path, args=["commit", "-m", "init"])


def _new_workspace(*, repo: Path, env: dict[str, str], branch: str) -> Path:
    result = subprocess.run(
        ["gitcuttle", "new", "-b", branch, "--destination"],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    assert result.returncode == 0
    return Path(result.stdout.strip())


def _write_fake_gh(*, directory: Path, script_body: str) -> None:
    gh_path = directory / "gh"
    gh_path.write_text(script_body)
    gh_path.chmod(0o755)


def _base_env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")
    return env


def _write_counting_fake_gh(*, directory: Path, count_file: Path) -> None:
    _write_fake_gh(
        directory=directory,
        script_body=(
            "#!/bin/sh\n"
            f"COUNT_FILE=\"{count_file}\"\n"
            "count=0\n"
            "if [ -f \"$COUNT_FILE\" ]; then\n"
            "  count=$(cat \"$COUNT_FILE\")\n"
            "fi\n"
            "count=$((count + 1))\n"
            "printf '%s\\n' \"$count\" > \"$COUNT_FILE\"\n"
            "printf '[{\"state\":\"OPEN\",\"isDraft\":false,\"title\":\"PR call %s\",\"url\":\"https://github.com/acme/repo/pull/%s\"}]\\n' \"$count\" \"$count\"\n"
        ),
    )


def _run_list_twice_with_cache_clock(
    *,
    cwd: Path,
    env: dict[str, str],
    script_dir: Path,
    remote_times: tuple[float, float],
    pr_times: tuple[float, float],
) -> subprocess.CompletedProcess[str]:
    runner = script_dir / "run_list_twice.py"
    runner.write_text(
        "import sys\n"
        "from git_cuttle import orchestrator\n"
        "from git_cuttle.__main__ import main\n"
        f"remote_times = iter({remote_times!r})\n"
        f"pr_times = iter({pr_times!r})\n"
        "orchestrator.REMOTE_STATUS_CACHE.now = lambda: next(remote_times)\n"
        "orchestrator.PULL_REQUEST_STATUS_CACHE.now = lambda: next(pr_times)\n"
        "for marker in ('RUN1', 'RUN2'):\n"
        "    print(marker)\n"
        "    sys.argv = ['gitcuttle', 'list']\n"
        "    main()\n"
    )
    return subprocess.run(
        ["python", str(runner)],
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


@pytest.mark.integration
def test_list_renders_online_github_pr_status(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(cwd=tmp_path, args=["init", "--bare", str(remote)])

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["remote", "add", "origin", str(remote)])
    _git(cwd=repo, args=["push", "-u", "origin", "main"])

    env = _base_env(tmp_path)
    workspace_path = _new_workspace(repo=repo, env=env, branch="feature/list-online")
    _git(cwd=workspace_path, args=["push", "-u", "origin", "feature/list-online"])
    _git(
        cwd=repo,
        args=["remote", "set-url", "origin", "https://github.com/acme/repo.git"],
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_fake_gh(
        directory=fake_bin,
        script_body="#!/bin/sh\n"
        'printf \'[{"state":"OPEN","isDraft":false,"title":"Add list coverage","url":"https://github.com/acme/repo/pull/1"}]\'\n',
    )
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    result = subprocess.run(
        ["gitcuttle", "list"],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0
    assert "REPO" in result.stdout
    assert "DIRTY" in result.stdout
    assert "DESCRIPTION" in result.stdout
    assert "feature/list-online" in result.stdout
    assert "open" in result.stdout
    assert "Add list coverage" in result.stdout


@pytest.mark.integration
def test_list_shows_unknown_marker_when_gh_is_offline(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(cwd=tmp_path, args=["init", "--bare", str(remote)])

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["remote", "add", "origin", str(remote)])
    _git(cwd=repo, args=["push", "-u", "origin", "main"])

    env = _base_env(tmp_path)
    workspace_path = _new_workspace(repo=repo, env=env, branch="feature/list-offline")
    _git(cwd=workspace_path, args=["push", "-u", "origin", "feature/list-offline"])
    _git(
        cwd=repo,
        args=["remote", "set-url", "origin", "https://github.com/acme/repo.git"],
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_fake_gh(directory=fake_bin, script_body="#!/bin/sh\nexit 1\n")
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    result = subprocess.run(
        ["gitcuttle", "list"],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0
    assert "feature/list-offline" in result.stdout
    assert " ? " in result.stdout


@pytest.mark.integration
def test_list_shows_unknown_marker_when_gh_is_unauthenticated(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(cwd=tmp_path, args=["init", "--bare", str(remote)])

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["remote", "add", "origin", str(remote)])
    _git(cwd=repo, args=["push", "-u", "origin", "main"])

    env = _base_env(tmp_path)
    workspace_path = _new_workspace(repo=repo, env=env, branch="feature/list-unauth")
    _git(cwd=workspace_path, args=["push", "-u", "origin", "feature/list-unauth"])
    _git(
        cwd=repo,
        args=["remote", "set-url", "origin", "https://github.com/acme/repo.git"],
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_fake_gh(
        directory=fake_bin,
        script_body="#!/bin/sh\n" "printf 'authentication failed' >&2\n" "exit 1\n",
    )
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    result = subprocess.run(
        ["gitcuttle", "list"],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0
    assert "feature/list-unauth" in result.stdout
    assert " ? " in result.stdout


@pytest.mark.integration
def test_list_shows_unknown_marker_for_non_github_remote(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(cwd=tmp_path, args=["init", "--bare", str(remote)])

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["remote", "add", "origin", str(remote)])
    _git(cwd=repo, args=["push", "-u", "origin", "main"])

    env = _base_env(tmp_path)
    workspace_path = _new_workspace(repo=repo, env=env, branch="feature/list-non-gh")
    _git(cwd=workspace_path, args=["push", "-u", "origin", "feature/list-non-gh"])

    result = subprocess.run(
        ["gitcuttle", "list"],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )

    assert result.returncode == 0
    assert "feature/list-non-gh" in result.stdout
    assert " ? " in result.stdout


@pytest.mark.integration
def test_list_reuses_status_cache_within_ttl(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(cwd=tmp_path, args=["init", "--bare", str(remote)])

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["remote", "add", "origin", str(remote)])
    _git(cwd=repo, args=["push", "-u", "origin", "main"])

    env = _base_env(tmp_path)
    workspace_path = _new_workspace(repo=repo, env=env, branch="feature/list-cache-ttl")
    _git(cwd=workspace_path, args=["push", "-u", "origin", "feature/list-cache-ttl"])
    _git(
        cwd=repo,
        args=["remote", "set-url", "origin", "https://github.com/acme/repo.git"],
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    count_file = tmp_path / "gh-count.txt"
    _write_counting_fake_gh(directory=fake_bin, count_file=count_file)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    result = _run_list_twice_with_cache_clock(
        cwd=repo,
        env=env,
        script_dir=tmp_path,
        remote_times=(100.0, 120.0),
        pr_times=(100.0, 120.0),
    )

    assert result.returncode == 0
    assert count_file.read_text().strip() == "1"
    assert result.stdout.count("PR call 1") == 2


@pytest.mark.integration
def test_list_refreshes_status_cache_after_ttl_expiry(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(cwd=tmp_path, args=["init", "--bare", str(remote)])

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _git(cwd=repo, args=["remote", "add", "origin", str(remote)])
    _git(cwd=repo, args=["push", "-u", "origin", "main"])

    env = _base_env(tmp_path)
    workspace_path = _new_workspace(
        repo=repo,
        env=env,
        branch="feature/list-cache-refresh",
    )
    _git(cwd=workspace_path, args=["push", "-u", "origin", "feature/list-cache-refresh"])
    _git(
        cwd=repo,
        args=["remote", "set-url", "origin", "https://github.com/acme/repo.git"],
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    count_file = tmp_path / "gh-count.txt"
    _write_counting_fake_gh(directory=fake_bin, count_file=count_file)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    result = _run_list_twice_with_cache_clock(
        cwd=repo,
        env=env,
        script_dir=tmp_path,
        remote_times=(100.0, 161.0),
        pr_times=(100.0, 161.0),
    )

    assert result.returncode == 0
    assert count_file.read_text().strip() == "2"
    assert "PR call 1" in result.stdout
    assert "PR call 2" in result.stdout
