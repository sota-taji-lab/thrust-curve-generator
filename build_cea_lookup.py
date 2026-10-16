"""Optionally prefill and validate the disk lookup before running a sweep.

Example: python build_cea_lookup.py --pc-min 250 --pc-max 550 --of-min 2 --of-max 6
Pressure bounds are absolute psia. An interrupted build can be resumed safely.
"""

import argparse
import math

import matlab.engine

import cea_lookup_config as cfg
from cea_lookup import CeaLookup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pc-min", "pc-max", "of-min", "of-max"):
        parser.add_argument("--" + name, type=float, required=True)
    args = parser.parse_args()
    if not 0 < args.pc_min < args.pc_max or not 0 < args.of_min < args.of_max:
        parser.error("Use positive bounds with max greater than min")
    print("Starting MATLAB...")
    eng = matlab.engine.start_matlab()
    lookup = CeaLookup(eng, "PARAFFIN", "LOX", mode="lookup")
    try:
        p_start = max(1, math.floor(args.pc_min / cfg.PRESSURE_STEP_PSIA))
        p_stop = math.ceil(args.pc_max / cfg.PRESSURE_STEP_PSIA)
        o_start = max(1, math.floor(args.of_min / cfg.OF_STEP))
        o_stop = math.ceil(args.of_max / cfg.OF_STEP)
        for pi in range(p_start, p_stop):
            for oi in range(o_start, o_stop):
                lookup.get((pi + .5) * cfg.PRESSURE_STEP_PSIA,
                           (oi + .5) * cfg.OF_STEP)
            print(f"Cell row {pi - p_start + 1}/{p_stop - p_start}: {lookup.stats}", flush=True)
        print(f"Saved lookup: {lookup.db_path}")
        print(f"Total: {lookup.stats}")
    finally:
        lookup.close()
        eng.quit()


if __name__ == "__main__":
    main()
