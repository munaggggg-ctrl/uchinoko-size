"""
schema + seed から実データDBを組み立てる。

DBはGitに置かない（差分が読めないバイナリを履歴に残さないため）。
そのかわり、schema.sql と seed_*.sql から毎回同じDBを作れるようにしてある。
CI では実行のたびに作り直す。手元でも同じコマンドで再現できる。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"
DEFAULT_SEED = ROOT / "data" / "seed_real.sql"
DEFAULT_OUT = ROOT / "data" / "real.db"


class BuildError(RuntimeError):
    pass


def build(out: Path = DEFAULT_OUT, seed: Path = DEFAULT_SEED) -> Path:
    for p in (SCHEMA, seed):
        if not p.exists():
            raise BuildError(f"{p} がありません")

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    con = sqlite3.connect(str(out))
    try:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        con.executescript(seed.read_text(encoding="utf-8"))
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM size_variant").fetchone()[0]
        b = con.execute("SELECT COUNT(*) FROM brand").fetchone()[0]
    finally:
        con.close()

    if n == 0:
        raise BuildError("サイズ行が0件です。seed を確認してください")
    print(f"build_db: {out} を作成しました（{b}ブランド / {n}行）")
    return out


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else DEFAULT_OUT
    try:
        build(out)
    except BuildError as e:
        print(f"NG: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
