"""Tests for Suno song request parsing."""

from pathlib import Path

import pytest

from suno_assistant.requests import MAX_REQUEST_COUNT, SongRequest, SongRequestError, load_song_request


class TestSongRequest:
    """Song request validation tests."""

    def test_from_prompt_uses_safe_defaults(self) -> None:
        """A one-line prompt should produce the simplest valid request."""
        request = SongRequest.from_prompt("An original piano ballad about finishing a long journey.")

        assert request.prompt == "An original piano ballad about finishing a long journey."
        assert request.count == 1
        assert request.tags == []
        assert request.instrumental is False
        assert request.custom_mode is False

    def test_from_mapping_parses_structured_request(self) -> None:
        """Structured YAML fields should map onto typed request attributes."""
        request = SongRequest.from_mapping(
            {
                "prompt": "An original synth pop song about a careful launch.",
                "title": "Careful Launch",
                "style": "synth pop, bright chorus",
                "lyrics": "We count down slowly",
                "custom_mode": True,
                "count": 2,
                "tags": ["mvp", "demo"],
                "notes": "local note",
            }
        )

        assert request.title == "Careful Launch"
        assert request.style == "synth pop, bright chorus"
        assert request.lyrics == "We count down slowly"
        assert request.custom_mode is True
        assert request.count == 2
        assert request.tags == ["mvp", "demo"]
        assert request.notes == "local note"

    def test_from_mapping_parses_advanced_controls(self) -> None:
        """Advanced-mode fields should map onto typed request attributes."""
        request = SongRequest.from_mapping(
            {
                "prompt": "An original art pop song about a careful launch.",
                "advanced_mode": True,
                "style": "art pop, odd percussion, warm synths",
                "lyrics": "We launch when the signal is clear",
                "exclude_styles": "metal, harsh noise",
                "vocal_gender": "Female",
                "style_mode": "Manual",
                "weirdness": 65,
                "style_influence": 80,
            }
        )

        assert request.advanced_mode is True
        assert request.uses_advanced_controls is True
        assert request.exclude_styles == "metal, harsh noise"
        assert request.vocal_gender == "female"
        assert request.style_mode == "manual"
        assert request.weirdness == 65
        assert request.style_influence == 80

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ({"prompt": ""}, "prompt must not be empty"),
            ({"prompt": "valid", "count": 0}, f"count must be between 1 and {MAX_REQUEST_COUNT}"),
            ({"prompt": "valid", "count": MAX_REQUEST_COUNT + 1}, f"count must be between 1 and {MAX_REQUEST_COUNT}"),
            ({"prompt": "valid", "instrumental": True, "lyrics": "words"}, "lyrics cannot be provided"),
            ({"prompt": "valid", "unknown": "field"}, "Unknown request field"),
            ({"prompt": "valid", "tags": ["ok", ""]}, "tags must be a list of non-empty strings"),
            ({"prompt": "valid", "instrumental": "false"}, "instrumental must be a boolean"),
            ({"prompt": "valid", "vocal_gender": "both"}, "vocal_gender must be one of"),
            ({"prompt": "valid", "style_mode": "sometimes"}, "style_mode must be one of"),
            ({"prompt": "valid", "weirdness": 101}, "weirdness must be between 0 and 100"),
            ({"prompt": "valid", "style_influence": "high"}, "style_influence must be an integer"),
        ],
    )
    def test_from_mapping_rejects_invalid_requests(self, raw: dict, message: str) -> None:
        """Invalid request data should raise clear validation errors."""
        with pytest.raises(SongRequestError, match=message):
            SongRequest.from_mapping(raw)

    @pytest.mark.parametrize(
        "prompt",
        [
            "Write a song in the style of a famous singer.",
            "Make it sound like a current pop star.",
            "Use the voice of a known artist.",
        ],
    )
    def test_rejects_restricted_artist_imitation_phrases(self, prompt: str) -> None:
        """Prompt guardrails should reject explicit artist or voice imitation requests."""
        with pytest.raises(SongRequestError, match="without asking to imitate"):
            SongRequest.from_prompt(prompt)


class TestLoadSongRequest:
    """Request file loader tests."""

    def test_load_song_request_reads_yaml_mapping(self, tmp_path: Path) -> None:
        """The loader should parse and validate YAML request files."""
        path = tmp_path / "request.yaml"
        path.write_text(
            "prompt: An original folk song about crossing a bridge.\n"
            "style: acoustic folk\n"
            "count: 1\n"
            "tags:\n"
            "  - local\n",
            encoding="utf-8",
        )

        request = load_song_request(path)

        assert request.prompt == "An original folk song about crossing a bridge."
        assert request.style == "acoustic folk"
        assert request.tags == ["local"]

    def test_load_song_request_rejects_missing_file(self) -> None:
        """Missing request files should raise a request-layer error."""
        with pytest.raises(SongRequestError, match="Request file not found"):
            load_song_request("missing.yaml")

    def test_load_song_request_rejects_non_mapping_yaml(self, tmp_path: Path) -> None:
        """The YAML request root must be a mapping."""
        path = tmp_path / "request.yaml"
        path.write_text("- prompt\n", encoding="utf-8")

        with pytest.raises(SongRequestError, match="YAML mapping"):
            load_song_request(path)
