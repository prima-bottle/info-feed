"""工作安排的加密 / 解密。仓库是公开的，所以工作安排只以加密形式存在 docs/work.enc 里。

  python tools/work_crypt.py encrypt plan.json docs/work.enc   （会提示输入密码）
  python tools/work_crypt.py decrypt docs/work.enc plan.json

格式与网页里的解密代码一一对应：PBKDF2-SHA256（25 万次）派生密钥，AES-256-GCM 加密。
"""
from __future__ import annotations

import base64
import getpass
import json
import os
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITER = 250_000


def _key(pw: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw.encode())


def encrypt(data: bytes, pw: str) -> dict:
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(pw, salt)).encrypt(iv, data, None)
    b = lambda x: base64.b64encode(x).decode()  # noqa: E731
    return {"v": 1, "iter": ITER, "salt": b(salt), "iv": b(iv), "ct": b(ct)}


def decrypt(box: dict, pw: str) -> bytes:
    d = base64.b64decode
    return AESGCM(_key(pw, d(box["salt"]))).decrypt(d(box["iv"]), d(box["ct"]), None)


def main() -> None:
    cmd, src, dst = sys.argv[1:4]
    pw = os.environ.get("WORK_PASS") or getpass.getpass("密码：")
    if cmd == "encrypt":
        plan = json.loads(open(src, encoding="utf-8").read())
        out = encrypt(json.dumps(plan, ensure_ascii=False).encode(), pw)
        open(dst, "w").write(json.dumps(out))
    elif cmd == "decrypt":
        open(dst, "w", encoding="utf-8").write(
            json.dumps(json.loads(decrypt(json.load(open(src)), pw)), ensure_ascii=False, indent=1))
    else:
        raise SystemExit("用法：encrypt|decrypt 输入 输出")


if __name__ == "__main__":
    main()
