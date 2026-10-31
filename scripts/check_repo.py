"""Small tracked-tree checks. Do not print secret values in diagnostics."""
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 5 * 1024 * 1024
SECRET_PATTERNS = {
    "Codyssey key": re.compile(r"\bsk-cody-live-[A-Za-z0-9]{16,}\b"),
    "OpenAI project key": re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "private key": re.compile(r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----"),
    "embedded service key": re.compile(r"(?i)serviceKey=[A-Za-z0-9%+/=_-]{35,}"),
}
CONFLICT = re.compile(r"^(?:<{7}|={7}|>{7})(?: |$)", re.MULTILINE)


def forbidden_path(path):
    p = PurePosixPath(path)
    name = p.name.lower()
    example = name.endswith((".example", ".template", ".sample"))
    if not example and (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith(".env")
        or name.startswith(".config.env")
    ):
        return "local credentials/configuration"
    if any(part in {"node_modules", ".venv", "venv", "__pycache__", ".secrets", "secrets"} for part in p.parts):
        return "local environment"
    if path.startswith(("work/", "outputs/", "data/", "app/data/", "상담메모/", "상담준비/")):
        return "runtime or personal data"
    if name.startswith("이음온_상담준비") and name.endswith(".txt"):
        return "private consultation export"
    if name.endswith((".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")):
        return "database or key material"
    return None


def text_findings(content):
    result = [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(content)]
    if CONFLICT.search(content):
        result.append("unresolved merge conflict")
    return result


def main():
    tracked = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=ROOT)
    failures = []
    for raw in tracked.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8")
        path = ROOT / name
        reason = forbidden_path(name)
        if reason:
            failures.append((name, reason))
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_BYTES:
            failures.append((name, "file exceeds 5 MiB; use appropriate artifact storage"))
            continue
        try:
            content = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            continue
        failures.extend((name, reason) for reason in text_findings(content))
    if failures:
        for name, reason in failures:
            print(f"ERROR: {name}: {reason}", file=sys.stderr)
        return 1
    print("Repository hygiene checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

