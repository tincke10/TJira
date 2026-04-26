"""Tests for ``tjira.profiles`` — the TOML-backed profile store.

These tests never touch the real ``~/.config/tjira/`` — every store is
constructed against a path under ``tmp_path``.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from tjira.errors import UserError
from tjira.profiles import (
    Profile,
    ProfileStore,
    default_config_path,
    validate_domain,
    validate_profile_name,
)


# ====================== default_config_path ======================


def test_default_config_path_honors_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "tjira" / "config.toml"


def test_default_config_path_falls_back_to_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert default_config_path() == tmp_path / ".config" / "tjira" / "config.toml"


# ====================== load ======================


def test_load_returns_empty_store_when_file_missing(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    store = ProfileStore.load(path)
    assert store.is_empty()
    assert store.current is None
    assert store.names() == []


def test_load_reads_profiles_and_current(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'current_profile = "work"\n'
        "\n"
        "[profiles.work]\n"
        'domain = "company.atlassian.net"\n'
        'email = "me@company.com"\n'
        'api_token = "tok-work"\n'
        "\n"
        "[profiles.personal]\n"
        'domain = "personal.atlassian.net"\n'
        'email = "me@gmail.com"\n'
        'api_token = "tok-personal"\n',
        encoding="utf-8",
    )
    store = ProfileStore.load(path)
    assert store.current == "work"
    assert store.names() == ["personal", "work"]
    work = store.get("work")
    assert work == Profile("work", "company.atlassian.net", "me@company.com", "tok-work")


def test_load_without_current_profile_field(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[profiles.solo]\n"
        'domain = "x.atlassian.net"\n'
        'email = "x@x.com"\n'
        'api_token = "t"\n',
        encoding="utf-8",
    )
    store = ProfileStore.load(path)
    assert store.current is None
    assert store.names() == ["solo"]


def test_load_raises_user_error_on_malformed_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("this is not = valid = toml\n[oops", encoding="utf-8")
    with pytest.raises(UserError) as exc_info:
        ProfileStore.load(path)
    assert "malformed" in exc_info.value.message.lower() or "parse" in exc_info.value.message.lower()
    assert exc_info.value.payload.get("path") == str(path)


def test_load_raises_user_error_when_profile_section_missing_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[profiles.broken]\n"
        'email = "x@x.com"\n',
        encoding="utf-8",
    )
    with pytest.raises(UserError) as exc_info:
        ProfileStore.load(path)
    payload = exc_info.value.payload
    assert payload.get("profile") == "broken"
    assert "domain" in payload.get("missing", [])
    assert "api_token" in payload.get("missing", [])


# ====================== save ======================


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "tjira" / "config.toml"
    store = ProfileStore(path=path)
    store.add(Profile("work", "company.atlassian.net", "me@company.com", "tok"))
    store.save()
    assert path.exists()
    assert path.parent.is_dir()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions only")
def test_save_writes_with_0600_permissions(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    store = ProfileStore(path=path)
    store.add(Profile("work", "company.atlassian.net", "me@company.com", "tok"))
    store.save()
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions only")
def test_save_locks_parent_directory_to_0700(tmp_path: Path) -> None:
    """The leaf config dir is owner-only, hiding the file's existence from others."""
    path = tmp_path / "tjira" / "config.toml"
    store = ProfileStore(path=path)
    store.add(Profile("work", "company.atlassian.net", "me@company.com", "tok"))
    store.save()
    mode = stat.S_IMODE(os.stat(path.parent).st_mode)
    assert mode == 0o700


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    store = ProfileStore(path=path)
    store.add(Profile("work", "company.atlassian.net", "me@company.com", "tok-work"))
    store.add(Profile("personal", "personal.atlassian.net", "me@gmail.com", "tok-personal"))
    store.set_current("work")
    store.save()

    reloaded = ProfileStore.load(path)
    assert reloaded.current == "work"
    assert reloaded.names() == ["personal", "work"]
    assert reloaded.get("work") == store.get("work")
    assert reloaded.get("personal") == store.get("personal")


def test_save_overwrites_existing_file_atomically(tmp_path: Path) -> None:
    """Save must replace contents wholesale; never append, never half-write."""
    path = tmp_path / "config.toml"
    path.write_text("garbage = true\n", encoding="utf-8")

    store = ProfileStore(path=path)
    store.add(Profile("only", "x.atlassian.net", "x@x.com", "t"))
    store.save()

    reloaded = ProfileStore.load(path)
    assert reloaded.names() == ["only"]


# ====================== add ======================


def test_add_inserts_new_profile() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    profile = Profile("work", "x.atlassian.net", "x@x.com", "t")
    store.add(profile)
    assert store.has("work")
    assert store.get("work") == profile


def test_add_raises_on_conflict_without_overwrite() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    store.add(Profile("work", "a.atlassian.net", "a@a.com", "t1"))
    with pytest.raises(UserError) as exc_info:
        store.add(Profile("work", "b.atlassian.net", "b@b.com", "t2"))
    assert "exists" in exc_info.value.message.lower() or "already" in exc_info.value.message.lower()
    assert exc_info.value.payload.get("profile") == "work"


def test_add_overwrites_when_flag_set() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    store.add(Profile("work", "a.atlassian.net", "a@a.com", "t1"))
    new = Profile("work", "b.atlassian.net", "b@b.com", "t2")
    store.add(new, overwrite=True)
    assert store.get("work") == new


# ====================== remove ======================


def test_remove_deletes_profile() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    store.add(Profile("work", "x.atlassian.net", "x@x.com", "t"))
    store.remove("work")
    assert not store.has("work")
    assert store.is_empty()


def test_remove_clears_current_if_it_was_active() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    store.add(Profile("work", "x.atlassian.net", "x@x.com", "t"))
    store.add(Profile("personal", "y.atlassian.net", "y@y.com", "t"))
    store.set_current("work")
    store.remove("work")
    assert store.current is None


def test_remove_keeps_current_if_other_profile_removed() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    store.add(Profile("work", "x.atlassian.net", "x@x.com", "t"))
    store.add(Profile("personal", "y.atlassian.net", "y@y.com", "t"))
    store.set_current("work")
    store.remove("personal")
    assert store.current == "work"


def test_remove_raises_when_profile_missing() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    with pytest.raises(UserError) as exc_info:
        store.remove("ghost")
    assert exc_info.value.payload.get("profile") == "ghost"


# ====================== set_current ======================


def test_set_current_changes_active() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    store.add(Profile("work", "x.atlassian.net", "x@x.com", "t"))
    store.add(Profile("personal", "y.atlassian.net", "y@y.com", "t"))
    store.set_current("personal")
    assert store.current == "personal"
    assert store.get_current() == store.get("personal")


def test_set_current_raises_for_unknown_profile() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    store.add(Profile("work", "x.atlassian.net", "x@x.com", "t"))
    with pytest.raises(UserError) as exc_info:
        store.set_current("ghost")
    assert exc_info.value.payload.get("profile") == "ghost"
    assert "work" in exc_info.value.payload.get("available", [])


# ====================== get / get_current ======================


def test_get_raises_with_available_names_in_payload() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    store.add(Profile("work", "x.atlassian.net", "x@x.com", "t"))
    store.add(Profile("personal", "y.atlassian.net", "y@y.com", "t"))
    with pytest.raises(UserError) as exc_info:
        store.get("ghost")
    assert sorted(exc_info.value.payload["available"]) == ["personal", "work"]


def test_get_current_returns_none_when_unset() -> None:
    store = ProfileStore(path=Path("/tmp/unused"))
    store.add(Profile("work", "x.atlassian.net", "x@x.com", "t"))
    assert store.get_current() is None


# ====================== validate_profile_name ======================


@pytest.mark.parametrize("name", ["work", "personal-2", "client_3", "v1.0", "x"])
def test_validate_profile_name_accepts_simple_identifiers(name: str) -> None:
    validate_profile_name(name)  # no raise


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        ".secret",
        "-leading-dash",
        "_leading-underscore",
        "../escape",
        "with space",
        "with/slash",
        "with\nnewline",
        "with\ttab",
        "with;semicolon",
        "with$dollar",
    ],
)
def test_validate_profile_name_rejects_invalid(name: str) -> None:
    with pytest.raises(UserError) as exc_info:
        validate_profile_name(name)
    assert exc_info.value.payload.get("name") == name


# ====================== validate_domain (security-critical) ======================


@pytest.mark.parametrize(
    "domain",
    [
        "company.atlassian.net",
        "personal.atlassian.net",
        "jira.example.com",
        "self-hosted.internal:8080",
        "x.y.z.example",
    ],
)
def test_validate_domain_accepts_bare_hosts(domain: str) -> None:
    validate_domain(domain)  # no raise


@pytest.mark.parametrize(
    "domain",
    [
        # URL hijacking attacks via @ (userinfo) — the host parses to the part AFTER @
        "real.atlassian.net@evil.com",
        "real.atlassian.net@evil.com:443",
        # Fragment / query / path tricks
        "evil.com#real.atlassian.net",
        "evil.com?host=real.atlassian.net",
        "evil.com/path/real.atlassian.net",
        "evil.com\\real.atlassian.net",
        # Schemes
        "https://x.atlassian.net",
        "http://x.atlassian.net",
        "://x.atlassian.net",
        # Whitespace / empty
        "",
        " ",
        " x.atlassian.net",
        "x.atlassian.net ",
        "x.atlassian.net\n",
        "x.atlassian.net\t",
        # Quote chars (could break TOML if it weren't escaped — defense in depth)
        'x.atlassian.net"',
        "x.atlassian.net'",
    ],
)
def test_validate_domain_rejects_dangerous(domain: str) -> None:
    with pytest.raises(UserError) as exc_info:
        validate_domain(domain)
    assert exc_info.value.payload.get("domain") == domain
