"""scripts/db_move.py: the db moves byte for byte, and the root password never rides an argv."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import db_move as dm  # noqa: E402


def test_the_dump_is_consistent_and_byte_exact_and_the_password_is_on_stdin() -> None:
    cmd = dm.dump_cmd("ragnarok")
    assert "--single-transaction" in cmd and "--default-character-set=binary" in cmd
    assert "--hex-blob" in cmd and cmd[-2:] == ["--databases", "ragnarok"]
    assert "--defaults-extra-file=/dev/stdin" in cmd
    restore = dm.restore_cmd()
    assert "--default-character-set=binary" in restore
    assert restore[-1] == f"source {dm.IN_CONTAINER}"
    secret = "pw-NOT-on-argv"
    cnf = dm.option_file({"DB_ROOT_PASSWORD": secret})
    assert cnf == f"[client]\nuser=root\npassword={secret}\n"
    assert not [a for a in [*cmd, *restore] if "password" in a.lower() and "defaults" not in a]
