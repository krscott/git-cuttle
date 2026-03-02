import pytest

from git_cuttle.lib import Options, greet


def test_greet(capsys: pytest.CaptureFixture[str]) -> None:
    greet(Options(name="World"))
    captured = capsys.readouterr()
    assert "Hello, World!" in captured.out
