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
        description="Encrypt dashboard HTML into .html2 for at-rest protection."
    )
    parser.add_argument(
        "--input",
        default="static/index.html",
        help="Input plaintext HTML path (default: static/index.html)",
    )
    parser.add_argument(
        "--output",
        default="static/index.html2",
        help="Output encrypted path (default: static/index.html2)",
    )
    parser.add_argument(
        "--key",
        default="",
        help="Fernet key. If omitted, DASHBOARD_CONTENT_KEY env is used.",
    )
    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Generate and print a new key, then use it for encryption.",
    )
    parser.add_argument(
        "--delete-source",
        action="store_true",
        help="Delete plaintext input file after successful encryption.",
    )
    return parser.parse_args()


def _resolve_key(args: argparse.Namespace) -> str:
    if args.generate_key:
        key = Fernet.generate_key().decode("utf-8")
        print("Generated DASHBOARD_CONTENT_KEY:")
        print(key)
        return key

    key = args.key.strip() or os.getenv("DASHBOARD_CONTENT_KEY", "").strip()
    if not key:
        raise SystemExit(
            "Missing key. Use --generate-key or set DASHBOARD_CONTENT_KEY in environment."
        )
    return key


def main() -> None:
    args = _parse_args()
    root = Path(__file__).resolve().parents[1]
    _load_local_env(root / ".env")
    key = _resolve_key(args)

    in_path = (root / args.input).resolve()
    out_path = (root / args.output).resolve()

    if not in_path.exists() or not in_path.is_file():
        raise SystemExit(f"Input file not found: {in_path}")

    plaintext = in_path.read_bytes()
    cipher = Fernet(key.encode("utf-8"))
    token = cipher.encrypt(plaintext)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(token)

    try:
        decrypted = cipher.decrypt(token)
        if decrypted != plaintext:
            raise SystemExit("Encryption verification failed: decrypted bytes differ.")
    except InvalidToken as exc:
        raise SystemExit(f"Encryption verification failed: {exc}") from exc

    print(f"Encrypted: {in_path}")
    print(f"Written:   {out_path}")

    if args.delete_source:
        in_path.unlink()
        print(f"Deleted plaintext source: {in_path}")

    print("Done. Set DASHBOARD_CONTENT_KEY in dashboards/hr/.env to the same key.")


if __name__ == "__main__":
    main()
