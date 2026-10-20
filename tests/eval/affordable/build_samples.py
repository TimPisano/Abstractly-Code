"""
Build every synthetic sample and answer key from specs/*.py.

  python -I tests/eval/affordable/build_samples.py            # all specs
  python -I tests/eval/affordable/build_samples.py tic_sc     # one spec

Deterministic: same specs + same sources -> same answer keys. Re-run after
editing a spec; commit the regenerated samples/ alongside it.
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fill_lib import build, build_acroform  # noqa: E402


def load_specs(only=None):
    specs = []
    for path in sorted((HERE / "specs").glob("*.py")):
        if path.name.startswith("_"):
            continue
        if only and path.stem not in only:
            continue
        mod_spec = importlib.util.spec_from_file_location(f"specs.{path.stem}", path)
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)
        specs.append(module.SPEC)
    return specs


def main(argv):
    specs = load_specs(set(argv) or None)
    if not specs:
        print("no specs matched", argv)
        return 1
    for spec in specs:
        key = build(spec)
        acro = build_acroform(spec)
        print(f"built {key['sample_file']}: {len(key['program_fields'])} program fields, "
              f"{sum(1 for v in key['lease_fields'].values() if v is not None)} lease fields"
              + (f" (+ {acro.name})" if acro else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
