#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_TEST_ROOT = ROOT / "tests"
BACKEND_UNIT_ROOT = BACKEND_TEST_ROOT / "unit"
BACKEND_INTEGRATION_ROOT = BACKEND_TEST_ROOT / "integration"
BACKEND_ALLOWED = {BACKEND_UNIT_ROOT, BACKEND_INTEGRATION_ROOT}
VENV_ROOT = ROOT / ".venv"
FRONTEND_ROOT = ROOT / "web-ui"
FRONTEND_UNIT_ROOT = FRONTEND_ROOT / "tests" / "unit"
FRONTEND_E2E_ROOT = FRONTEND_ROOT / "tests" / "e2e"


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def validate_backend() -> int:
    if not BACKEND_UNIT_ROOT.exists() or not BACKEND_INTEGRATION_ROOT.exists():
        return fail("Backend test directories tests/unit and tests/integration must exist.")

    exit_code = 0
    for path in BACKEND_ALLOWED:
        if not path.exists():
            exit_code |= fail(f"Missing required backend test directory: {path.relative_to(ROOT)}")

    for py_file in ROOT.glob("**/test_*.py"):
        if "web-ui" in py_file.parts:
            continue
        if VENV_ROOT in py_file.parents:
            continue
        if not any(py_file.is_relative_to(allowed) for allowed in BACKEND_ALLOWED):
            exit_code |= fail(
                f"Backend test file {py_file.relative_to(ROOT)} is outside tests/unit or tests/integration"
            )
    for path in BACKEND_TEST_ROOT.rglob("*.py"):
        if path.name.startswith("test_") or path.name in {"conftest.py"} or path.name.startswith("_"):
            continue
        if any(path.is_relative_to(allowed) for allowed in BACKEND_ALLOWED):
            exit_code |= fail(
                f"Backend test file {path.relative_to(ROOT)} must use test_*.py naming."
            )
    return exit_code


def validate_frontend() -> int:
    exit_code = 0
    if not FRONTEND_UNIT_ROOT.exists():
        exit_code |= fail("Missing web-ui/tests/unit directory")
    if not FRONTEND_E2E_ROOT.exists():
        exit_code |= fail("Missing web-ui/tests/e2e directory")

    for test_file in FRONTEND_ROOT.glob("**/*.test.ts*"):
        if "node_modules" in test_file.parts:
            continue
        if not test_file.is_relative_to(FRONTEND_UNIT_ROOT):
            exit_code |= fail(
                f"Frontend unit test {test_file.relative_to(FRONTEND_ROOT)} must reside in tests/unit"
            )

    for e2e_file in FRONTEND_ROOT.glob("**/*.e2e.spec.ts"):
        if "node_modules" in e2e_file.parts:
            continue
        if not e2e_file.is_relative_to(FRONTEND_E2E_ROOT):
            exit_code |= fail(
                f"Frontend e2e spec {e2e_file.relative_to(FRONTEND_ROOT)} must reside in tests/e2e"
            )

    for extraneous in FRONTEND_E2E_ROOT.rglob("*"):
        if extraneous.is_file() and extraneous.name not in {'.gitkeep'} and not extraneous.name.endswith(".e2e.spec.ts"):
            exit_code |= fail(
                f"Files in tests/e2e must end with .e2e.spec.ts (found {extraneous.relative_to(FRONTEND_ROOT)})"
            )
    return exit_code


def main() -> int:
    exit_code = 0
    exit_code |= validate_backend()
    exit_code |= validate_frontend()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
