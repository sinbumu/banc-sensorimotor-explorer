"""Interactive local credential setup. Run yourself; never pass tokens as arguments."""

import getpass
import json
import re
from pathlib import Path


def main():
    target = Path.home() / ".cloudvolume" / "secrets" / "cave.fanc-fly.com-cave-secret.json"
    if target.exists():
        print("The host-specific CAVE credential file already exists; leaving it unchanged.")
        print(target)
        return 1
    print("Use your existing BANC-authorized CAVE token. Input is hidden and stays on this PC.")
    token = getpass.getpass("CAVE token: ")
    if not re.fullmatch(r"[!-~]{1,8192}", token):
        print("Invalid/empty token; no file written.")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create avoids overwriting a credential created during the prompt.
    with target.open("x", encoding="utf-8") as stream:
        json.dump({"token": token}, stream)
        stream.write("\n")
    print("Saved local CAVE credential (value hidden):")
    print(target)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, EOFError, KeyboardInterrupt):
        raise SystemExit(
            "CAVE setup was interrupted or the credential file could not be written."
        ) from None
