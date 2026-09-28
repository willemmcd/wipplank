"""Inline OpenPGP via the gpg binary. Optional: pip install wipplank[openpgp].

v1 scope is body-only (inline, RFC 1847 style like classic MUAs):
attachments are never encrypted/signed. Key management (gen/import/
trust) stays in `gpg` itself — we only use existing keys.
"""
import os

PGP_SIGNED = "-----BEGIN PGP SIGNED MESSAGE-----"
PGP_MESSAGE = "-----BEGIN PGP MESSAGE-----"


def _gpg(gnupghome: str | None = None):
    try:
        import gnupg
    except ImportError:
        raise SystemExit("OpenPGP needs python-gnupg. Run: pip install 'wipplank[openpgp]'")
    try:
        g = gnupg.GPG(gnupghome=gnupghome) if gnupghome else gnupg.GPG()
    except Exception as e:
        raise SystemExit(f"gpg binary not usable: {e}")
    import shutil

    gbin = getattr(g, "gpgbinary", None) or getattr(g, "binary", None) or "gpg"
    if not shutil.which(str(gbin).split()[0]):
        raise SystemExit("gpg binary not found. Install GnuPG first (brew install gnupg).")
    return g


def detect(body: str) -> str:
    if PGP_MESSAGE in (body or ""):
        return "encrypted"
    if PGP_SIGNED in (body or ""):
        return "signed"
    return "plain"


def list_secret_keys(gnupghome: str | None = None) -> list[dict]:
    g = _gpg(gnupghome)
    return [{"fingerprint": k.get("fingerprint", ""), "uids": k.get("uids", [])}
            for k in g.list_keys(secret=True)]


def sign(body: str, keyid: str | None = None, passphrase: str | None = None,
         gnupghome: str | None = None) -> str:
    g = _gpg(gnupghome)
    if not list_secret_keys(gnupghome):
        raise SystemExit("No PGP secret keys. Create one with: gpg --quick-generate-key you@example.com")
    signed = g.sign(body, keyid=keyid, passphrase=passphrase, clearsign=True)
    if not signed or not str(signed).strip():
        raise SystemExit(f"Signing failed: {signed.status or 'unknown error'}")
    return str(signed)


def encrypt(body: str, recipients: list[str], sign: str | None = None,
            passphrase: str | None = None, trust: bool = False,
            gnupghome: str | None = None) -> str:
    g = _gpg(gnupghome)
    enc = g.encrypt(body, recipients=recipients, sign=sign, passphrase=passphrase,
                    always_trust=trust)
    if not enc or not str(enc).strip():
        raise SystemExit(f"Encryption failed: {enc.status or 'unknown error (key trusted?)'}")
    return str(enc)


def decrypt(body: str, passphrase: str | None = None,
            gnupghome: str | None = None) -> str:
    g = _gpg(gnupghome)
    dec = g.decrypt(body, passphrase=passphrase)
    if not dec or not str(dec).strip():
        raise SystemExit(f"Decryption failed: {dec.status or 'wrong key/passphrase?'}")
    return str(dec)


def verify(body: str, gnupghome: str | None = None) -> dict:
    g = _gpg(gnupghome)
    v = g.verify(body)
    return {
        "signed": PGP_SIGNED in (body or ""),
        "valid": bool(v and v.valid),
        "fingerprint": getattr(v, "fingerprint", "") or "",
        "username": getattr(v, "username", "") or "",
        "status": getattr(v, "status", "") or "",
    }
