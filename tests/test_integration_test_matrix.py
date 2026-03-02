import re
from pathlib import Path

MATRIX_PATH = Path(__file__).resolve().parent.parent / "INTEGRATION_TEST_MATRIX.md"
SECTIONS_REQUIRING_COVERAGE = {
    "## Workspace command contracts",
    "## Safety, transactions, and rollback",
}


def _collect_test_functions() -> set[str]:
    tests_dir = Path(__file__).resolve().parent
    test_functions: set[str] = set()
    for path in tests_dir.glob("test_*.py"):
        for line in path.read_text().splitlines():
            match = re.match(r"def (test_[a-zA-Z0-9_]+)\(", line)
            if match is None:
                continue
            test_functions.add(f"tests/{path.name}::{match.group(1)}")
    return test_functions


def _covered_rows_for_section(section_name: str) -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
    lines = MATRIX_PATH.read_text().splitlines()
    in_section = False
    status_idx: int | None = None
    reference_idx: int | None = None

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if line.startswith("## "):
            in_section = line == section_name
            status_idx = None
            reference_idx = None
            continue
        if not in_section or not line.startswith("|"):
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if "Status" in cells:
            status_idx = cells.index("Status")
            reference_idx = len(cells) - 1
            continue
        if status_idx is None or reference_idx is None:
            continue
        if set("".join(cells)) == {"-"}:
            continue

        status = cells[status_idx]
        reference = cells[reference_idx]
        rows.append((line_no, status, reference))
    return rows


def test_workspace_and_safety_rows_are_not_marked_planned() -> None:
    planned_lines: list[int] = []
    for section in SECTIONS_REQUIRING_COVERAGE:
        for line_no, status, _ in _covered_rows_for_section(section):
            if status == "planned":
                planned_lines.append(line_no)

    assert not planned_lines, (
        "Expected workspace/safety requirements to be marked covered; "
        f"found planned rows at lines {planned_lines}."
    )


def test_workspace_and_safety_coverage_references_existing_tests() -> None:
    known_tests = _collect_test_functions()
    missing: list[str] = []

    for section in SECTIONS_REQUIRING_COVERAGE:
        for line_no, status, reference in _covered_rows_for_section(section):
            if status != "covered":
                continue
            refs = re.findall(r"tests/[a-zA-Z0-9_./-]+::test_[a-zA-Z0-9_]+", reference)
            if not refs:
                missing.append(f"line {line_no}: missing test reference")
                continue
            for ref in refs:
                if ref not in known_tests:
                    missing.append(f"line {line_no}: unknown test '{ref}'")

    assert not missing, "Invalid integration matrix references:\n" + "\n".join(missing)
