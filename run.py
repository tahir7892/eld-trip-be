#!/usr/bin/env python3
"""
Bootstrap and run the Django development server.

Uses the project virtual environment, applies migrations, then starts runserver.

Usage:
    python run.py
    python run.py 8001
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def find_venv_python() -> Path:
    """Return the Python executable inside the local virtual environment."""
    candidates = []
    if sys.platform == "win32":
        candidates = [
            ROOT / "env" / "Scripts" / "python.exe",
            ROOT / "venv" / "Scripts" / "python.exe",
        ]
    else:
        candidates = [
            ROOT / "env" / "bin" / "python",
            ROOT / "venv" / "bin" / "python",
        ]

    for python_path in candidates:
        if python_path.is_file():
            return python_path

    names = ", ".join(str(p.relative_to(ROOT)) for p in candidates)
    print("Virtual environment not found.")
    print(f"Expected one of: {names}")
    print("Create it with: python3 -m venv env && pip install -r requirements.txt")
    sys.exit(1)


def run_manage(python: Path, *args: str) -> None:
    """Run a manage.py command with the venv Python."""
    cmd = [str(python), "manage.py", *args]
    print(f"\n→ {' '.join(cmd)}\n")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    python = find_venv_python()
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"

    os.chdir(ROOT)
    os.environ["VIRTUAL_ENV"] = str(python.parent.parent)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    print(f"Using virtualenv Python: {python}")

    run_manage(python, "migrate")
    run_manage(python, "runserver", port)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)
