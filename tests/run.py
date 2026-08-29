"""最小のテストランナー。pytest が無い環境でも走らせるための代替。"""
import importlib.util
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    passed, failed = 0, []
    for path in sorted(HERE.glob("test_*.py")):
        mod = load(path)
        for name in sorted(vars(mod)):
            if not name.startswith("test_"):
                continue
            fn = getattr(mod, name)
            if not callable(fn):
                continue
            try:
                fn()
                passed += 1
            except Exception:
                failed.append((path.name, name, traceback.format_exc()))

    for file, name, tb in failed:
        print(f"\n--- FAIL {file}::{name} ---\n{tb}")

    print(f"\n{passed} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
