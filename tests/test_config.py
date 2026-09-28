from wipplank import config as cfgmod


def test_migrate_legacy_folds_into_default_account():
    cfgmod.save_config({"default_backend": "imap", "imap": {
        "host": "h", "port": 993, "username": "u@x",
        "smtp_host": "s", "smtp_port": 587, "from_addr": "u@x"}})
    cfgmod.save_password("u@x", "pw")
    assert cfgmod.migrate_legacy() is True
    assert cfgmod.migrate_legacy() is False  # idempotent
    acct = cfgmod.get_account("default")
    assert acct["type"] == "imap" and acct["host"] == "h"
    assert cfgmod.get_account_password("default") == "pw"
    assert cfgmod.get_default_account() == "default"
    assert cfgmod.get_imap_config()["username"] == "u@x"  # legacy read-through


def test_account_crud_and_default():
    cfgmod.save_account("w", {"type": "imap", "username": "w@x"})
    assert "w" in cfgmod.list_accounts()
    assert cfgmod.get_default_account() == "w"  # first account wins
    cfgmod.save_account("g", {"type": "gmail", "email": "g@y"})
    cfgmod.delete_account("w")
    assert "w" not in cfgmod.list_accounts()
    assert cfgmod.delete_account("nope") is False


def test_keyring_round_trip():
    cfgmod.save_account_password("a", "s3cret")
    assert cfgmod.get_account_password("a") == "s3cret"
    cfgmod.delete_account_password("a")
    assert cfgmod.get_account_password("a") is None


def test_brand_migration_copies_config_and_reads_old_keyring(tmp_path, monkeypatch):
    import keyring

    # simulate a pre-rename home: old config file + old-service secret,
    # pointed at temp paths so the real home is untouched
    old_cfg = tmp_path / "oldcfg.json"
    old_cfg.write_text('{"default_account": "w", "accounts": {"w": {"type": "imap"}}}')
    monkeypatch.setattr(cfgmod, "LEGACY_CONFIG_FILES", [old_cfg])
    monkeypatch.setattr(cfgmod, "CONFIG_FILE", tmp_path / "newcfg.json")
    keyring.set_password("agentmail", "account:w", "oldsecret")
    try:
        assert cfgmod.load_config()["default_account"] == "w"  # copied over
        assert cfgmod.get_account_password("w") == "oldsecret"  # old-service fallback
    finally:
        keyring.delete_password("agentmail", "account:w")
