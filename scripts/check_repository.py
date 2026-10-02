"""Audit publishable/staged files without printing potential secret values."""

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2_000_000
FORBIDDEN_DIRS = {".cache", ".tools", ".venv", ".godot", ".aws", ".cave", "__pycache__"}
DATA_EXTENSIONS = {".feather", ".parquet", ".arrow", ".swc", ".glb", ".gltf", ".bin"}
BINARY_EXTENSIONS = {".exe", ".dll", ".zip", ".7z", ".tar", ".gz", ".pck"}
SECRET_EXTENSIONS = {".token", ".pem", ".key", ".p12", ".pfx"}
SECRET_PATTERNS = [
    rb"gh[pousr]_[A-Za-z0-9]{30,}",
    rb"github_pat_[A-Za-z0-9_]{30,}",
    rb"\bAKIA[0-9A-Z]{16}\b",
    rb"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}",
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def audit(staged=False):
    names = (
        git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
        if staged
        else git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    )
    failures, total, count = [], 0, 0
    for raw in sorted(set(names.split(b"\0")) - {b""}):
        name = raw.decode("utf-8")
        path = Path(name)
        content = git("show", f":{name}") if staged else (ROOT / path).read_bytes()
        count += 1
        total += len(content)
        fixture = path.as_posix().startswith("tests/fixtures/") and len(content) < 64_000
        reasons = []
        if FORBIDDEN_DIRS.intersection(path.parts):
            reasons.append("cache/tool/credential directory")
        if path.parts[0] == "generated" and path.as_posix() != "generated/.gitkeep":
            reasons.append("generated artifact")
        if path.suffix.lower() in DATA_EXTENSIONS and not fixture:
            reasons.append("raw data or geometry")
        if path.suffix.lower() in BINARY_EXTENSIONS:
            reasons.append("executable/archive")
        if (
            path.suffix.lower() in SECRET_EXTENSIONS
            or path.name.startswith(".env")
            or path.name in {"cave-secret.json", "export_credentials.cfg"}
        ):
            reasons.append("credential filename")
        if len(content) > MAX_BYTES:
            reasons.append("file exceeds 2 MB publish budget")
        if any(re.search(pattern, content) for pattern in SECRET_PATTERNS):
            reasons.append("possible embedded secret (value withheld)")
        if reasons:
            failures.append(f"{name}: {', '.join(reasons)}")
    print(f"Audited {count} {'staged' if staged else 'publishable'} files / {total:,} bytes.")
    for failure in failures:
        print(f"REJECT: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Read the exact Git index content")
    raise SystemExit(audit(parser.parse_args().staged))
