"""CLI end-to-end on the demo backend with isolated config."""
import json

from wipplank.cli import app


def _run(runner, *args):
    r = runner.invoke(app, ["--backend", "demo", *args])
    assert r.exit_code == 0, r.output
    return r


def test_check_read_search_json(cli_runner):
    out = json.loads(_run(cli_runner, "check", "--json").output)
    assert [m["id"] for m in out] == ["demo-1", "demo-2", "demo-3"]
    one = json.loads(_run(cli_runner, "read", "demo-1", "--json").output)
    assert one["subject"].startswith("Welcome")
    hits = json.loads(_run(cli_runner, "search", "rocket", "--json").output)
    assert [m["id"] for m in hits] == ["demo-3"]


def test_send_dry_run_and_noattach_guard(cli_runner):
    r = cli_runner.invoke(app, ["--backend", "demo", "send", "--to", "t@x",
                                "-s", "hi", "--body", "see attached"])
    assert r.exit_code != 0 and "attach" in r.output.lower()
    out = json.loads(_run(cli_runner, "send", "--to", "t@x", "-s", "hi",
                          "--body", "yo", "--dry-run", "--json").output)
    assert out["dry_run"] is True and out["to"] == "t@x"


def test_reply_forward_dry_run_threading(cli_runner):
    out = json.loads(_run(cli_runner, "reply", "demo-1", "--body", "Ta. ",
                          "--dry-run", "--json").output)
    assert out["subject"].startswith("Re:") and "> Welcome!" in out["body"]
    out = json.loads(_run(cli_runner, "forward", "demo-1", "--to", "f@x",
                          "--dry-run", "--json").output)
    assert out["subject"].startswith("Fwd:")


def test_mark_and_saved_and_templates(cli_runner):
    assert json.loads(_run(cli_runner, "mark", "demo-1", "--flag", "--json").output) == {
        "flagged": {"demo-1": True}}
    _run(cli_runner, "saved", "save", "n", "rocket")
    assert "n" in json.loads(_run(cli_runner, "saved", "list", "--json").output)
    assert [m["id"] for m in json.loads(
        _run(cli_runner, "saved", "run", "n", "--json").output)] == ["demo-3"]
    _run(cli_runner, "saved", "rm", "n")
    _run(cli_runner, "template", "save", "t", "-s", "Hi {to}", "--body", "Yo {to}")
    out = json.loads(_run(cli_runner, "send", "--to", "bob", "--template", "t",
                          "--dry-run", "--json").output)
    assert out["subject"] == "Hi bob" and out["body"] == "Yo bob"
    _run(cli_runner, "signature", "set", "Sig")
    out = json.loads(_run(cli_runner, "send", "--to", "bob", "-s", "s",
                          "--body", "b", "--dry-run", "--json").output)
    assert out["body"].endswith("-- \nSig")
    _run(cli_runner, "send", "--to", "bob", "-s", "s",
         "--body", "b", "--save-draft", "d")
    assert "d" in json.loads(_run(cli_runner, "draft", "list", "--json").output)
    _run(cli_runner, "draft", "rm", "d")


def test_account_and_misc(cli_runner):
    from wipplank import config as cfgmod

    r = _run(cli_runner, "account", "list")
    assert r.exit_code == 0  # empty isolated config
    cfgmod.save_account("w", {"type": "imap", "username": "w@x"})
    assert "w" in _run(cli_runner, "account", "list").output
    status = json.loads(_run(cli_runner, "auth", "status", "--json").output)
    assert status["active_backend"] == "demo"
    _run(cli_runner, "cache-clear")
    assert "attach" in _run(cli_runner, "send", "--help").output
    _run(cli_runner, "attach", "list", "demo-1")
    _run(cli_runner, "mcp", "--help")
    _run(cli_runner, "tui", "--help")
