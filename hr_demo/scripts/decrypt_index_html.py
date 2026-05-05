from __future__ import annotations

import argparse
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _load_local_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Decrypt dashboard .html2 back to plaintext HTML."
    )
    parser.add_argument(
        "--input",
        default="static/index.html2",
        help="Encrypted input path (default: static/index.html2)",
    )
    parser.add_argument(
        "--output",
        default="static/index.decrypted.html",
        help="Plaintext output path (default: static/index.decrypted.html)",
    )
    parser.add_argument(
        "--key",
        default="",
        help="Fernet key. If omitted, DASHBOARD_CONTENT_KEY env is used.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    _load_local_env(root / ".env")
    key = args.key.strip() or os.getenv("DASHBOARD_CONTENT_KEY", "").strip()
    if not key:
        raise SystemExit("Missing key. Use --key or set DASHBOARD_CONTENT_KEY.")

    in_path = (root / args.input).resolve()
    out_path = (root / args.output).resolve()

    if not in_path.exists() or not in_path.is_file():
        raise SystemExit(f"Encrypted input not found: {in_path}")

    cipher = Fernet(key.encode("utf-8"))
    token = in_path.read_bytes()

    try:
        plaintext = cipher.decrypt(token)
    except InvalidToken as exc:
        raise SystemExit("Invalid key or corrupted encrypted file.") from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(plaintext)

    print(f"Decrypted: {in_path}")
    print(f"Written:   {out_path}")


if __name__ == "__main__":
    main()
