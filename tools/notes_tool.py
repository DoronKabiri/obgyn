#!/usr/bin/env python3
"""Read the site's encrypted notes/usage file (notes/notes.json.enc in the public repo).

The page saves, per topic, the doctor's free-text note and usage counters (views, copies) per device,
encrypted with the site password (same AES-256-GCM / PBKDF2 scheme as the vault).
Usage:  notes_tool.py            -> print usage ranking + all notes
        notes_tool.py --json     -> dump the decrypted JSON
Config: ~/.config/obgyn-vault-mailer/config.json (password, owner, repo, iterations)
"""
import json, sys, time, urllib.request, ssl
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

CONF = Path.home() / ".config" / "obgyn-vault-mailer" / "config.json"


def ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def main():
    cfg = json.loads(CONF.read_text(encoding="utf-8"))
    url = f"https://raw.githubusercontent.com/{cfg['owner']}/{cfg['repo']}/main/notes/notes.json.enc?t={int(time.time())}"
    req = urllib.request.Request(url, headers={"User-Agent": "obgyn-notes-tool", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx()) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("no notes file yet"); return 0
        raise
    salt, iv, ct = blob[:16], blob[16:28], blob[28:]
    key = PBKDF2HMAC(algorithm=SHA256(), length=32, salt=salt, iterations=int(cfg.get("iterations", 250000))).derive(cfg["password"].encode())
    data = json.loads(AESGCM(key).decrypt(iv, ct, None).decode("utf-8"))
    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=1)); return 0
    views, copies = {}, {}
    for dev, d in (data.get("devices") or {}).items():
        for k, v in (d.get("views") or {}).items(): views[k] = views.get(k, 0) + int(v)
        for k, v in (d.get("copies") or {}).items(): copies[k] = copies.get(k, 0) + int(v)
    print(f"updated: {data.get('updatedAt')}   devices: {len(data.get('devices') or {})}")
    print("\n== usage ranking (copies, views) ==")
    for k in sorted(set(views) | set(copies), key=lambda k: (-(copies.get(k, 0)), -(views.get(k, 0)))):
        print(f"{copies.get(k, 0):4d} {views.get(k, 0):4d}  {k}")
    notes = data.get("notes") or {}
    print(f"\n== notes ({sum(1 for n in notes.values() if (n.get('text') or '').strip())}) ==")
    for k, n in sorted(notes.items(), key=lambda kv: kv[1].get("updatedAt", 0), reverse=True):
        if (n.get("text") or "").strip():
            print(f"\n## {k}  ({time.strftime('%d.%m.%Y %H:%M', time.localtime((n.get('updatedAt') or 0) / 1000))})\n{n['text'].strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
