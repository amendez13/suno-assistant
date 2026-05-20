"""Tests for release metadata helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from tests.module_loader import import_source_module

release_info_module = import_source_module("release_info")


def test_get_release_info_prefers_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("RELEASE_TAG", "v1.2.3")
    monkeypatch.setenv("RELEASE_COMMIT", "abc123456789")

    info = release_info_module.get_release_info()

    assert info == {
        "tag": "v1.2.3",
        "commit": "abc123456789",
        "short_commit": "abc1234",
        "source": "env",
    }


def test_get_release_info_falls_back_to_git(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("RELEASE_TAG", raising=False)
    monkeypatch.delenv("RELEASE_COMMIT", raising=False)

    def fake_run(args, cwd, capture_output, text, timeout, check):  # type: ignore[no-untyped-def]
        command = tuple(args[1:])
        outputs = {
            ("rev-parse", "HEAD"): "abc123456789\n",
            ("rev-parse", "--short", "HEAD"): "abc1234\n",
            ("describe", "--tags", "--exact-match"): "v1.2.3\n",
        }
        stdout = outputs.get(command, "")
        return SimpleNamespace(returncode=0 if stdout else 1, stdout=stdout)

    monkeypatch.setattr(release_info_module.subprocess, "run", fake_run)

    info = release_info_module.get_release_info()

    assert info == {
        "tag": "v1.2.3",
        "commit": "abc123456789",
        "short_commit": "abc1234",
        "source": "git",
    }


def test_get_release_info_falls_back_to_version_file(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("RELEASE_TAG", raising=False)
    monkeypatch.delenv("RELEASE_COMMIT", raising=False)
    monkeypatch.setattr(release_info_module, "_git_output", lambda *args: None)

    version_file = tmp_path / "VERSION"
    version_file.write_text("v9.9.9\n", encoding="utf-8")
    monkeypatch.setattr(release_info_module, "_VERSION_FILE", version_file)

    info = release_info_module.get_release_info()

    assert info == {
        "tag": "v9.9.9",
        "commit": None,
        "short_commit": None,
        "source": "version_file",
    }


def test_git_output_returns_none_on_subprocess_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.SubprocessError("git failed")

    monkeypatch.setattr(release_info_module.subprocess, "run", fake_run)

    assert release_info_module._git_output("rev-parse", "HEAD") is None


def test_git_output_returns_none_on_nonzero_exit(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace(returncode=1, stdout="ignored")

    monkeypatch.setattr(release_info_module.subprocess, "run", fake_run)

    assert release_info_module._git_output("describe", "--tags", "--exact-match") is None


def test_version_file_value_returns_none_on_read_error(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    missing_file = tmp_path / "missing" / "VERSION"
    monkeypatch.setattr(release_info_module, "_VERSION_FILE", missing_file)

    assert release_info_module._version_file_value() is None


def test_get_release_info_returns_unknown_without_sources(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("RELEASE_TAG", raising=False)
    monkeypatch.delenv("RELEASE_COMMIT", raising=False)
    monkeypatch.setattr(release_info_module, "_git_output", lambda *args: None)
    monkeypatch.setattr(release_info_module, "_version_file_value", lambda: None)

    assert release_info_module.get_release_info() == {
        "tag": None,
        "commit": None,
        "short_commit": None,
        "source": "unknown",
    }
