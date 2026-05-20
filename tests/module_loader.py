"""Helpers for importing source modules from the template or a rendered project."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import ModuleType


def import_source_module(module_name: str) -> ModuleType:
    """Import a source module even after the source directory is renamed."""
    try:
        return import_module(f"src.{module_name}")
    except ModuleNotFoundError as exc:
        repo_root = Path(__file__).resolve().parent.parent
        for candidate in sorted(repo_root.iterdir()):
            if not candidate.is_dir():
                continue
            if not (candidate / "__init__.py").exists():
                continue
            if not (candidate / f"{module_name}.py").exists():
                continue
            return import_module(f"{candidate.name}.{module_name}")
        raise exc
