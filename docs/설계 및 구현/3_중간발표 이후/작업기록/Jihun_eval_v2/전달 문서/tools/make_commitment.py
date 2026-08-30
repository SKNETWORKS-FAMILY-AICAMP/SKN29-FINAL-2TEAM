#!/usr/bin/env python3
"""Agent Eval V2 HOLDOUT — private package commitment generator.

Computes opaque HMAC commitments for fixture.yaml, gold.yaml, and the whole
private package directory, per
01_HOLDOUT_비공개_문제_제작_가이드.md 3.7 ("UTF-8·LF와 정렬된 canonical form을
기준으로 HMAC commitment를 만든다").

Run this ONLY inside the access-restricted private repository. Never run it
against a checkout that also contains the public repo, and never print or log
the secret key or the raw canonical bytes.

Usage:
    python3 make_commitment.py \
        --secret path/to/hmac_secret.key \
        --fixture path/to/fixture.yaml \
        --gold path/to/gold.yaml \
        --package-dir path/to/package_root

Only the three printed *_commitment values are safe to paste into
04_public_manifest.template.yaml. Nothing else this script prints (if you add
debug output) should ever leave the private repo.
"""

import argparse
import hashlib
import hmac
import os
import sys


def canonicalize_file(path: str) -> bytes:
    """UTF-8 read, normalize line endings to LF, strip trailing whitespace per
    line and a single trailing newline at EOF. This is the 'canonical form'
    the guide refers to — deterministic regardless of the editor/OS that
    last touched the file."""
    with open(path, "r", encoding="utf-8", newline=None) as f:
        text = f.read()
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    canonical = "\n".join(lines) + "\n"
    return canonical.encode("utf-8")


def canonicalize_dir(root: str) -> bytes:
    """Canonical form of an entire directory: sorted relative file paths,
    each paired with its own canonical (or raw, for binary source files)
    content hash, concatenated deterministically. This lets the whole
    package (fixture + gold + sources/ + manifests) be committed to as one
    unit without loading everything into memory at once."""
    entries = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            entries.append(rel)
    entries.sort()

    h = hashlib.sha256()
    for rel in entries:
        full = os.path.join(root, rel)
        try:
            content_hash = hashlib.sha256(canonicalize_file(full)).digest()
        except UnicodeDecodeError:
            # binary file (e.g. a source PDF) — hash raw bytes instead
            with open(full, "rb") as f:
                content_hash = hashlib.sha256(f.read()).digest()
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(content_hash)
        h.update(b"\x00")
    return h.digest()


def load_secret(path: str) -> bytes:
    with open(path, "r", encoding="utf-8") as f:
        secret_hex = f.read().strip()
    return bytes.fromhex(secret_hex)


def commit(secret: bytes, label: str, payload: bytes) -> str:
    mac = hmac.new(secret, payload, hashlib.sha256)
    # label goes in as HMAC input too, so the same content under a different
    # role (fixture vs gold vs package) never collides in the commitment.
    mac.update(label.encode("utf-8"))
    return "hmac-sha256:" + mac.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--secret", required=True, help="path to hmac_secret.key (hex-encoded)")
    ap.add_argument("--fixture", required=True, help="path to fixture.yaml")
    ap.add_argument("--gold", required=True, help="path to gold.yaml")
    ap.add_argument("--package-dir", required=True, help="path to the package root directory")
    args = ap.parse_args()

    secret = load_secret(args.secret)

    fixture_commitment = commit(secret, "fixture", canonicalize_file(args.fixture))
    gold_commitment = commit(secret, "gold", canonicalize_file(args.gold))
    package_commitment = commit(secret, "package", canonicalize_dir(args.package_dir))

    print("fixture_commitment:", fixture_commitment)
    print("gold_commitment:", gold_commitment)
    print("private_package_commitment:", package_commitment)
    print("\n위 세 줄만 04_public_manifest.template.yaml에 붙여넣으세요.", file=sys.stderr)
    print("이 스크립트의 다른 출력이나 --secret 파일 내용은 절대 공개 저장소로 옮기지 마세요.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
