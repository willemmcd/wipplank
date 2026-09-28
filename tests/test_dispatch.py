import pytest

from wipplank.backends import get_backend


def test_dispatch_demo_imap_unknown():
    assert get_backend("demo").name == "demo"
    with pytest.raises(ValueError, match="unknown backend"):
        get_backend("nope")


def test_dispatch_account_paths():
    from wipplank import config as cfgmod

    cfgmod.save_account("w", {"type": "imap", "host": "h", "port": 993,
                              "username": "u", "smtp_host": "s", "smtp_port": 587})
    cfgmod.save_account_password("w", "pw")
    be = get_backend("demo", account="w")
    assert be.name == "imap" and be.username == "u"
    with pytest.raises(ValueError, match="unknown account"):
        get_backend("demo", account="ghost")
    cfgmod.save_account("g", {"type": "weird"})
    with pytest.raises(ValueError, match="unknown type"):
        get_backend("demo", account="g")


def test_mcp_resolve(monkeypatch):
    from wipplank import config as cfgmod
    from wipplank.mcp_server import _resolve

    assert _resolve() == (None, "demo")  # empty isolated config
    cfgmod.save_account("w", {"type": "imap", "username": "u"})
    cfg = cfgmod.load_config()
    cfg["default_account"] = "w"
    cfgmod.save_config(cfg)
    assert _resolve() == ("w", "demo")
    monkeypatch.setenv("WIPPLANK_ACCOUNT", "w")
    assert _resolve()[0] == "w"
