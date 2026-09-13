from __future__ import annotations

import pytest

from day37_bank_qa.settings import Settings


def test_database_defaults_only_target_windows_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("DAY37_SERVICE_HOST", "ES_URL", "REDIS_HOST", "NEO4J_URI"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VM_HOST", "192.168.220.77")

    settings = Settings.from_env()

    assert settings.es_url == "http://127.0.0.1:19200"
    assert settings.redis_host == "127.0.0.1"
    assert settings.neo4j_uri == "bolt://127.0.0.1:7689"
    assert settings.vm_host == "192.168.220.77"


def test_service_host_can_be_overridden_without_changing_vm_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DAY37_SERVICE_HOST", "127.0.0.2")
    monkeypatch.setenv("VM_HOST", "192.168.220.88")
    for name in ("ES_URL", "REDIS_HOST", "NEO4J_URI"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.es_url == "http://127.0.0.2:19200"
    assert settings.redis_host == "127.0.0.2"
    assert settings.neo4j_uri == "bolt://127.0.0.2:7689"
    assert settings.vm_host == "192.168.220.88"
