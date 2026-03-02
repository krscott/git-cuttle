from dataclasses import dataclass


@dataclass(kw_only=True, frozen=True)
class AppError:
    code: str
    message: str
    guidance: tuple[str, ...] = ()
    details: str | None = None


def format_user_error(error: AppError) -> str:
    lines = [f"error[{error.code}]: {error.message}"]
    if error.details:
        lines.append(f"details: {error.details}")
    lines.extend(f"hint: {hint}" for hint in error.guidance)
    return "\n".join(lines)
