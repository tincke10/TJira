"""Tests for ``tjira.config`` — profile resolution + ``--profile`` override."""

from __future__ import annotations

from pathlib import Path

import pytest

from tjira import config as cfg
from tjira.errors import UserError
from tjira.profiles import Profile, ProfileStore


def _seed(tmp_path: Path, *profiles: Profile, current: str | None) -> ProfileStore:
    store = ProfileStore(path=tmp_path / "tjira" / "config.toml")
    for prof in profiles:
        store.add(prof)
    if current is not None:
        store.set_current(current)
    store.save()
    return store


# ====================== resolve_profile ======================


def test_resolve_profile_returns_active_profile(tmp_path: Path) -> None:
    work = Profile("work", "company.atlassian.net", "me@company.com", "tok")
    _seed(tmp_path, work, current="work")
    assert cfg.resolve_profile() == work


def test_resolve_profile_uses_override_when_set(tmp_path: Path) -> None:
    work = Profile("work", "company.atlassian.net", "me@company.com", "tok-w")
    personal = Profile("personal", "personal.atlassian.net", "me@gmail.com", "tok-p")
    _seed(tmp_path, work, personal, current="work")

    cfg.set_profile_override("personal")
    try:
        assert cfg.resolve_profile() == personal
    finally:
        cfg.set_profile_override(None)


def test_resolve_profile_raises_when_override_missing(tmp_path: Path) -> None:
    work = Profile("work", "company.atlassian.net", "me@company.com", "tok")
    _seed(tmp_path, work, current="work")

    cfg.set_profile_override("ghost")
    try:
        with pytest.raises(UserError) as exc_info:
            cfg.resolve_profile()
    finally:
        cfg.set_profile_override(None)
    assert exc_info.value.payload["profile"] == "ghost"
    assert "work" in exc_info.value.payload["available"]


def test_resolve_profile_raises_when_no_profiles(tmp_path: Path) -> None:
    with pytest.raises(UserError) as exc_info:
        cfg.resolve_profile()
    assert "profile add" in exc_info.value.payload["hint"]


def test_resolve_profile_raises_when_no_active_selected(tmp_path: Path) -> None:
    work = Profile("work", "company.atlassian.net", "me@company.com", "tok")
    _seed(tmp_path, work, current=None)
    with pytest.raises(UserError) as exc_info:
        cfg.resolve_profile()
    assert "switch" in exc_info.value.payload["hint"]
    assert "work" in exc_info.value.payload["available"]


# ====================== set/get_profile_override ======================


def test_override_round_trip() -> None:
    cfg.set_profile_override("foo")
    assert cfg.get_profile_override() == "foo"
    cfg.set_profile_override(None)
    assert cfg.get_profile_override() is None


def test_override_empty_string_normalized_to_none() -> None:
    cfg.set_profile_override("")
    assert cfg.get_profile_override() is None


# ====================== has_any_profile ======================


def test_has_any_profile_false_when_empty(tmp_path: Path) -> None:
    assert cfg.has_any_profile() is False


def test_has_any_profile_true_when_one_exists(tmp_path: Path) -> None:
    _seed(tmp_path, Profile("solo", "x.atlassian.net", "x@x.com", "t"), current=None)
    assert cfg.has_any_profile() is True
