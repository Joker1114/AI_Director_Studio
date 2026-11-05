"""Create a reproducible source-only archive from the repository root."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "AI_Director_Studio_V1.1_Electron_Cloud_API_Source.zip"
EXCLUDED_DIRS = {
    ".git", "node_modules", "__pycache__", ".pytest_cache", "build", "dist", "out",
    "release", ".venv", "data", ".ruff_cache", ".mypy_cache",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3"}


def main() -> None:
    files = sorted(
        file for file in ROOT.rglob("*")
        if file.is_file()
        and not any(part in EXCLUDED_DIRS for part in file.relative_to(ROOT).parts)
        and file.suffix not in EXCLUDED_SUFFIXES
        and file.name != ".env"
    )
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, arcname=str(Path(ROOT.name) / file.relative_to(ROOT)))
    print(f"Created: {OUTPUT}")
    print(f"Source files: {len(files)}")
    print(f"Size: {OUTPUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
