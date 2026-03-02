from git_cuttle.errors import AppError, format_user_error


def test_format_user_error_includes_code_message_and_hints() -> None:
    formatted = format_user_error(
        AppError(
            code="example",
            message="something failed",
            guidance=("retry with --verbose", "check your git config"),
        )
    )

    assert formatted == (
        "error[example]: something failed\n"
        "hint: retry with --verbose\n"
        "hint: check your git config"
    )


def test_format_user_error_includes_details_when_present() -> None:
    formatted = format_user_error(
        AppError(
            code="bad-input",
            message="invalid branch name",
            details="branch cannot contain spaces",
        )
    )

    assert formatted == (
        "error[bad-input]: invalid branch name\n"
        "details: branch cannot contain spaces"
    )
