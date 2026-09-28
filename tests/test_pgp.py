"""PGP round-trip with a throwaway keyring. Marked slow (keygen ~seconds)."""
import shutil

import pytest

pytestmark = pytest.mark.slow

gpg_missing = shutil.which("gpg") is None
try:
    import gnupg  # noqa: F401
    gnupg_missing = False
except ImportError:
    gnupg_missing = True

needs_gpg = pytest.mark.skipif(gpg_missing or gnupg_missing, reason="needs gpg + python-gnupg")


@pytest.fixture(scope="module")
def keyring_home(request):
    # NOTE: short path on purpose — gpg-agent sockets break over ~100 chars,
    # which pytest's tmp dirs exceed on macOS.
    import shutil
    import tempfile

    home = tempfile.mkdtemp(prefix="amgpg")
    request.addfinalizer(lambda: shutil.rmtree(home, ignore_errors=True))
    with open(f"{home}/params", "w") as f:
        f.write("%no-protection\nKey-Type: RSA\nKey-Length: 2048\n"
                "Name-Real: Tester\nName-Email: tester@x\nExpire-Date: 0\n")
    import os as _os
    import subprocess

    env = dict(_os.environ, GNUPGHOME=home)
    subprocess.run(["gpg", "--batch", "--pinentry-mode", "loopback",
                    "--gen-key", f"{home}/params"],
                   check=True, env=env, capture_output=True)
    return home


@needs_gpg
def test_sign_verify(keyring_home):
    from wipplank import pgp

    s = pgp.sign("hello", gnupghome=keyring_home)
    assert pgp.detect(s) == "signed"
    v = pgp.verify(s, gnupghome=keyring_home)
    assert v["valid"] and "tester@x" in v["username"]


@needs_gpg
def test_encrypt_decrypt(keyring_home):
    from wipplank import pgp

    e = pgp.encrypt("secret", ["tester@x"], trust=True, gnupghome=keyring_home)
    assert pgp.detect(e) == "encrypted"
    assert pgp.decrypt(e, gnupghome=keyring_home) == "secret"


def test_detect_plain():
    from wipplank import pgp

    assert pgp.detect("hello") == "plain"
    assert pgp.detect("") == "plain"
