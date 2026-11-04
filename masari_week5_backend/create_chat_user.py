"""Provision a local hashed-password account without printing credentials."""

import argparse
import getpass
import json
import os
from pathlib import Path

from dotenv import dotenv_values, set_key

from security import USERNAME_PATTERN, hash_password, parse_users


def add_user(env_file: Path, username: str, password: str) -> None:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Invalid username.")
    if env_file.is_symlink() or env_file.name != ".env":
        raise ValueError("Use a regular, untracked .env file.")
    encoded = hash_password(password)
    values = dotenv_values(env_file, interpolate=False) if env_file.exists() else {}
    raw_users = values.get("CHAT_AUTH_USERS")
    users = parse_users(raw_users) if raw_users and raw_users != "{}" else {}
    users[username] = encoded
    # Enforce the same account/configuration validation used by the server.
    serialized = json.dumps(users, separators=(",", ":"))
    parse_users(serialized)
    if not env_file.exists():
        fd = os.open(env_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    os.chmod(env_file, 0o600)
    set_key(str(env_file), "CHAT_AUTH_USERS", serialized)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    password = getpass.getpass("New chat password (12–256 ASCII characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.exit(1, "Passwords do not match. No changes made.\n")
    try:
        add_user(Path(__file__).resolve().parent / ".env", args.username, password)
    except (OSError, ValueError):
        parser.exit(1, "Could not configure the account. Check the username and local .env.\n")
    print("Updated local .env authentication configuration. No credentials were printed.")


if __name__ == "__main__":
    main()
