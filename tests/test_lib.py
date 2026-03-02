from git_cuttle.lib import Options


def test_options_defaults() -> None:
    opts = Options()

    assert opts.branch is None
    assert opts.base_ref is None
    assert opts.parent_refs == ()
    assert not opts.destination
