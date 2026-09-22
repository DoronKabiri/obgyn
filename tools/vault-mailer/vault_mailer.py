#!/usr/bin/env python3
"""Vault mailer: email newly uploaded vault files (any type) to the site owner, once each.

Flow: list docs/ in the public repo -> for every *.enc not yet sent -> download,
decrypt with the site password (same AES-GCM/PBKDF2 scheme as the page) -> send as an
attachment through the local Gmail CLI -> record the file's sha in sent.json.

Config:  ~/.config/obgyn-vault-mailer/config.json  {password, to, iterations, owner, repo, dir}
State:   ~/.config/obgyn-vault-mailer/sent.json    {sha: {name, sent_at, message_id}} or {name, failures, last_error} (given up after 3)
Usage:   vault_mailer.py [--dry] [--resend NAME] [--local FILE.enc]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

CONF_DIR = Path.home() / ".config" / "obgyn-vault-mailer"
CONF = CONF_DIR / "config.json"
STATE = CONF_DIR / "sent.json"
GMAIL_DIR = Path.home() / "Desktop" / "Claude Folder" / "gmail-automation"
GMAIL_PY = GMAIL_DIR / ".venv" / "bin" / "python"
GMAIL_CLI = GMAIL_DIR / "inbox.py"


def log(msg: str) -> None:
    print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, STATE)


def ssl_context():
    """python.org builds ship without root certificates; prefer certifi's bundle when present."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL = None


def encode_url(url: str) -> str:
    """Percent-encode the path and query of a URL that may contain spaces or Hebrew (GitHub returns raw names)."""
    from urllib.parse import urlsplit, urlunsplit, quote
    u = urlsplit(url)
    return urlunsplit((u.scheme, u.netloc, quote(u.path, safe="/%"), quote(u.query, safe="=&?%"), u.fragment))


def gh_get(url: str) -> bytes:
    global _SSL
    if _SSL is None:
        _SSL = ssl_context()
    url = encode_url(url)
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "obgyn-vault-mailer",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=60, context=_SSL) as r:
        return r.read()


def list_vault(cfg: dict) -> list[dict]:
    url = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/contents/{cfg['dir']}?ref=main&t={int(time.time())}"
    try:
        items = json.loads(gh_get(url))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    return [it for it in items if it.get("type") == "file" and it["name"].endswith(".enc")]


def decrypt(blob: bytes, password: str, iterations: int) -> bytes:
    if len(blob) < 28 + 16:
        raise ValueError("file too short to be a vault file")
    salt, iv, ct = blob[:16], blob[16:28], blob[28:]
    key = PBKDF2HMAC(algorithm=SHA256(), length=32, salt=salt, iterations=iterations).derive(password.encode("utf-8"))
    return AESGCM(key).decrypt(iv, ct, None)


def send_email(to: str, subject: str, body: str, attachment: Path) -> str:
    cmd = [str(GMAIL_PY), str(GMAIL_CLI), "send", to, subject, "--body", body, "--attach", str(attachment)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(GMAIL_DIR))
    if res.returncode != 0:
        raise RuntimeError(f"gmail send failed: {res.stderr.strip()[-400:]}")
    out = json.loads(res.stdout.strip().splitlines()[-1])
    return out["message_id"]


def process(name: str, blob: bytes, cfg: dict, dry: bool) -> str | None:
    file_name = name[:-4] if name.endswith(".enc") else name
    plain = decrypt(blob, cfg["password"], int(cfg.get("iterations", 250000)))
    if dry:
        log(f"DRY: would send {file_name} ({len(plain)} bytes) to {cfg['to']}")
        return None
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / file_name
        path.write_bytes(plain)
        subject = f"כספת: {file_name}"
        body = (f"מצורף הקובץ {file_name} שהועלה לכספת האתר.\n"
                f"נשלח אוטומטית ב-{dt.datetime.now():%d.%m.%Y %H:%M}.\n")
        return send_email(cfg["to"], subject, body, path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="decrypt and report, do not send or record")
    ap.add_argument("--resend", metavar="NAME", help="send this vault file again even if already sent")
    ap.add_argument("--local", metavar="FILE", help="process one local .enc file instead of the vault (test)")
    args = ap.parse_args()

    cfg = load_json(CONF, None)
    if not cfg:
        log(f"missing config {CONF}")
        return 2
    if not GMAIL_PY.exists():
        log(f"gmail CLI python not found at {GMAIL_PY}")
        return 2

    if args.local:
        p = Path(args.local)
        mid = process(p.name, p.read_bytes(), cfg, args.dry)
        log(f"local test sent: {p.name} message_id={mid}" if mid else f"local test done: {p.name}")
        return 0

    state = load_json(STATE, {})
    try:
        items = list_vault(cfg)
    except Exception as e:  # network / rate limit: report and try again next run
        log(f"listing failed: {e}")
        return 1

    def pending(it):
        rec = state.get(it["sha"], {})
        return not rec.get("sent_at") and int(rec.get("failures", 0)) < 3
    todo = [it for it in items if pending(it) or (args.resend and it["name"] == args.resend)]
    if not todo:
        sent = sum(1 for r in state.values() if r.get("sent_at"))
        given_up = [r["name"] for r in state.values() if not r.get("sent_at") and int(r.get("failures", 0)) >= 3]
        log(f"no new files ({len(items)} in vault, {sent} sent" + (f", given up: {given_up}" if given_up else "") + ")")
        return 0

    failures = 0
    for it in todo:
        try:
            blob = gh_get(it["download_url"] + f"?t={int(time.time())}")
            mid = process(it["name"], blob, cfg, args.dry)
            if not args.dry:
                state[it["sha"]] = {"name": it["name"], "sent_at": dt.datetime.now().isoformat(timespec="seconds"), "message_id": mid}
                save_state(state)
                log(f"sent {it['name']} ({it['size']} bytes) message_id={mid}")
        except Exception as e:
            failures += 1
            log(f"FAILED {it['name']}: {e}")
            if not args.dry:
                rec = dict(state.get(it["sha"], {}))
                rec.update({"name": it["name"], "failures": int(rec.get("failures", 0)) + 1, "last_error": str(e)[:300]})
                state[it["sha"]] = rec
                save_state(state)
                if rec["failures"] >= 3:
                    log(f"giving up on {it['name']} after {rec['failures']} attempts; use --resend to retry")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
