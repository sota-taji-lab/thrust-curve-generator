"""External coarse/fine optimizer for the hybrid thrust-curve generator.

Usage
-----
    python sweep_runner.py --mode coarse
    python sweep_runner.py --mode fine
    python sweep_runner.py --mode all

The runner calls the same engine model as Streamlit directly.  It does not
control a browser or automate Streamlit widgets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import qmc

import model_runner
import sweep_config as cfg


PROJECT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_DIR / "sweep_results"


@lru_cache(maxsize=1)
def configuration_signature() -> str:
    """Reject fine mode when the engine source or sweep configuration changed."""
    settings = {
        name: getattr(cfg, name) for name in (
            "CHAMBER_PRESSURE_PSIG", "MIN_INJECTOR_STIFFNESS",
            "MAX_INITIAL_TANK_PRESSURE_PSIG", "FUEL_MASS_KG",
            "OXIDIZER_MASS_FLOW_KG_S", "INITIAL_PORT_DIAMETER_M",
            "GRAIN_MAX_OD_M", "GRAIN_LENGTH_MIN_M", "GRAIN_LENGTH_MAX_M",
            "BURN_TIME_MIN_S", "BURN_TIME_MAX_S",
            "SIZING_INITIAL_OXIDIZER_MASS_KG", "COARSE_CASES",
            "COARSE_MIN_CASES", "COARSE_TARGET_FEASIBLE", "SWEEP_MODEL_VERSION",
        )
    }
    digest = hashlib.sha256((PROJECT_DIR / "engine.py").read_bytes()).hexdigest()
    return hashlib.sha256((json.dumps(settings, sort_keys=True) + digest).encode()).hexdigest()

VARIABLES = (
    "chamber_pressure_psig",
    "fuel_mass_kg",
    "oxidizer_mdot_kg_s",
    "port_diameter_m",
    "injector_stiffness",
)

EFFECTIVE_PC_MAX_PSIG = min(
    cfg.CHAMBER_PRESSURE_PSIG[1],
    model_runner.max_chamber_pressure_psig(
        cfg.MAX_INITIAL_TANK_PRESSURE_PSIG, cfg.MIN_INJECTOR_STIFFNESS
    ),
)
if EFFECTIVE_PC_MAX_PSIG < cfg.CHAMBER_PRESSURE_PSIG[0]:
    raise ValueError("No chamber pressure fits the selected tank cap and minimum stiffness.")

GLOBAL_BOUNDS: Dict[str, Tuple[float, float]] = {
    "chamber_pressure_psig": (cfg.CHAMBER_PRESSURE_PSIG[0], EFFECTIVE_PC_MAX_PSIG),
    "fuel_mass_kg": cfg.FUEL_MASS_KG,
    "oxidizer_mdot_kg_s": cfg.OXIDIZER_MASS_FLOW_KG_S,
    "port_diameter_m": cfg.INITIAL_PORT_DIAMETER_M,
    "injector_stiffness": (
        cfg.MIN_INJECTOR_STIFFNESS,
        model_runner.injector_stiffness_from_pressures(
            cfg.CHAMBER_PRESSURE_PSIG[0], cfg.MAX_INITIAL_TANK_PRESSURE_PSIG
        ),
    ),
}


def stiffness_interval(bounds: Dict[str, Tuple[float, float]], pc_psig: float):
    """Feasible S interval at Pc; tank cap supplies its dynamic upper bound."""
    lower = bounds["injector_stiffness"][0]
    upper = min(
        bounds["injector_stiffness"][1],
        model_runner.injector_stiffness_from_pressures(
            pc_psig, cfg.MAX_INITIAL_TANK_PRESSURE_PSIG
        ),
    )
    if upper < lower - 1e-10:
        return None
    return lower, max(lower, upper)


def grain_length(candidate: Dict[str, float]) -> float:
    return model_runner.calculate_grain_length_m(
        candidate["fuel_mass_kg"],
        candidate["port_diameter_m"],
        cfg.GRAIN_MAX_OD_M,
        cfg.FUEL_DENSITY_KG_M3,
    )


def geometry_is_valid(candidate: Dict[str, float]) -> tuple[bool, float]:
    try:
        length = grain_length(candidate)
    except ValueError:
        return False, math.nan
    valid = cfg.GRAIN_LENGTH_MIN_M <= length <= cfg.GRAIN_LENGTH_MAX_M
    return valid, length


def _lhs_pool(
    bounds: Dict[str, Tuple[float, float]],
    n: int,
    seed: int,
) -> List[Dict[str, float]]:
    sampler = qmc.LatinHypercube(d=len(VARIABLES), seed=seed)
    sample = sampler.random(n=n)
    lows = np.array([bounds[name][0] for name in VARIABLES], dtype=float)
    highs = np.array([bounds[name][1] for name in VARIABLES], dtype=float)
    scaled = qmc.scale(sample, lows, highs)
    candidates = []
    for unit_row, row in zip(sample, scaled):
        candidate = {name: float(row[i]) for i, name in enumerate(VARIABLES)}
        interval = stiffness_interval(bounds, candidate["chamber_pressure_psig"])
        if interval is None:
            continue
        # Stratify a 0..1 fraction, then map it into the pressure-dependent
        # stiffness interval; do not clip candidates onto the tank cap.
        candidate["injector_stiffness"] = (
            interval[0] + unit_row[-1] * (interval[1] - interval[0])
        )
        candidates.append(candidate)
    return candidates


def _pc_boundary_anchors(bounds: Dict[str, Tuple[float, float]]) -> List[Dict[str, float]]:
    """Guarantee that the pressure endpoints are actually evaluated.

    LHS samples are interior points, so the Pc endpoints would not be tested
    exactly. Other variables are placed near their mid-ranges
    with a port diameter corresponding to a 0.91 m grain.
    """

    fuel = 0.5 * sum(bounds["fuel_mass_kg"])
    ox_mdot = 0.5 * sum(bounds["oxidizer_mdot_kg_s"])
    target_length = 0.5 * (cfg.GRAIN_LENGTH_MIN_M + cfg.GRAIN_LENGTH_MAX_M)
    port_sq = cfg.GRAIN_MAX_OD_M**2 - 4.0 * fuel / (
        math.pi * cfg.FUEL_DENSITY_KG_M3 * target_length
    )
    port = math.sqrt(port_sq)
    port = min(max(port, bounds["port_diameter_m"][0]), bounds["port_diameter_m"][1])

    anchors = []
    for pc in bounds["chamber_pressure_psig"]:
        interval = stiffness_interval(bounds, pc)
        if interval is not None:
            anchors.append({
                "chamber_pressure_psig": pc,
                "fuel_mass_kg": fuel,
                "oxidizer_mdot_kg_s": ox_mdot,
                "port_diameter_m": port,
                "injector_stiffness": 0.5 * (interval[0] + interval[1]),
            })
    return anchors


def generate_valid_candidates(
    target_count: int,
    bounds: Dict[str, Tuple[float, float]],
    seed: int,
) -> List[Dict[str, float]]:
    """Generate exactly target_count geometry- and pressure-valid design points."""

    valid: List[Dict[str, float]] = []
    seen = set()

    for anchor in _pc_boundary_anchors(bounds):
        ok, length = geometry_is_valid(anchor)
        if ok:
            anchor = dict(anchor)
            anchor["grain_length_m"] = length
            key = tuple(round(anchor[name], 12) for name in VARIABLES)
            if key not in seen:
                seen.add(key)
                valid.append(anchor)

    # Generate a larger LHS pool and filter by the derived grain-length limit.
    # If a highly restricted fine box is supplied, expand the pool as needed.
    attempt = 0
    pool_size = max(target_count * 6, 600)
    rng = np.random.default_rng(seed + 991)

    while len(valid) < target_count and attempt < 8:
        pool = _lhs_pool(bounds, pool_size, seed + attempt)
        filtered = []
        for candidate in pool:
            ok, length = geometry_is_valid(candidate)
            if not ok:
                continue
            candidate["grain_length_m"] = length
            key = tuple(round(candidate[name], 12) for name in VARIABLES)
            if key in seen:
                continue
            filtered.append(candidate)
            seen.add(key)

        needed = target_count - len(valid)
        if len(filtered) > needed:
            idx = rng.choice(len(filtered), size=needed, replace=False)
            valid.extend(filtered[i] for i in idx)
        else:
            valid.extend(filtered)

        attempt += 1
        pool_size *= 2

    if len(valid) < target_count:
        raise RuntimeError(
            f"Could only generate {len(valid)} geometry-valid cases; "
            f"{target_count} were requested. Check the sweep ranges."
        )

    return valid[:target_count]


def generate_mode_candidates(
    mode: str,
    target_count: int,
    bounds: Dict[str, Tuple[float, float]],
    seed: int,
) -> List[Dict[str, float]]:
    """Generate local Fine candidates, with an optional global reserve."""
    if mode != "fine":
        candidates = generate_valid_candidates(target_count, bounds, seed)
        return [dict(candidate, search_region="global") for candidate in candidates]

    if not 0.0 <= cfg.FINE_GLOBAL_FRACTION <= 1.0:
        raise ValueError("FINE_GLOBAL_FRACTION must be between 0 and 1.")
    global_count = round(target_count * cfg.FINE_GLOBAL_FRACTION)
    local_count = target_count - global_count
    candidates = []
    seen = set()
    for region, count, region_bounds, region_seed in (
        ("local", local_count, bounds, seed),
        ("global", global_count, GLOBAL_BOUNDS, seed + 73019),
    ):
        if count == 0:
            continue
        # A handful of spare candidates cover overlapping boundary anchors.
        pool = generate_valid_candidates(count + 8, region_bounds, region_seed)
        added = 0
        for candidate in pool:
            key = tuple(round(candidate[name], 12) for name in VARIABLES)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(dict(candidate, search_region=region))
            added += 1
            if added == count:
                break
        if added != count:
            raise RuntimeError(f"Could not generate enough distinct {region} fine candidates")
    return candidates


def coarse_coverage_reached(evaluated: int, feasible: int) -> bool:
    return (
        evaluated >= cfg.COARSE_MIN_CASES
        and evaluated % cfg.COARSE_CHECK_INTERVAL == 0
        and feasible >= cfg.COARSE_TARGET_FEASIBLE
    )


def candidate_to_inputs(candidate: Dict[str, float], ox_mass_kg: float) -> Dict[str, float]:
    values = model_runner.get_default_inputs()
    values.update(
        {
            "chamber_pressure": candidate["chamber_pressure_psig"],
            "target_press_psig": model_runner.tank_pressure_psig_from_stiffness(
                candidate["chamber_pressure_psig"], candidate["injector_stiffness"]
            ),
            "fuel_mass": candidate["fuel_mass_kg"],
            "ox_mdot": candidate["oxidizer_mdot_kg_s"],
            "port_diameter": candidate["port_diameter_m"],
            "grain_max_od": cfg.GRAIN_MAX_OD_M,
            "ox_mass": ox_mass_kg,
        }
    )
    return values


def _empty_record(case_id: int, mode: str, candidate: Dict[str, float]) -> Dict[str, object]:
    tank_pressure_psig = model_runner.tank_pressure_psig_from_stiffness(
        candidate["chamber_pressure_psig"], candidate["injector_stiffness"]
    )
    return {
        "case_id": case_id,
        "mode": mode,
        "search_region": candidate.get("search_region", "global"),
        "chamber_pressure_psig": candidate["chamber_pressure_psig"],
        "tank_pressure_psig": tank_pressure_psig,
        "injector_stiffness": candidate["injector_stiffness"],
        "injector_pressure_drop_psi": tank_pressure_psig - candidate["chamber_pressure_psig"],
        "minimum_injector_stiffness": cfg.MIN_INJECTOR_STIFFNESS,
        "max_initial_tank_pressure_psig": cfg.MAX_INITIAL_TANK_PRESSURE_PSIG,
        "tank_pressure_constraint_pass": tank_pressure_psig <= cfg.MAX_INITIAL_TANK_PRESSURE_PSIG + 1e-8,
        "sweep_model_version": cfg.SWEEP_MODEL_VERSION,
        "configuration_signature": configuration_signature(),
        "feasible": False,
        "error": "",
        "initial_fuel_mass_kg": candidate["fuel_mass_kg"],
        "initial_oxidizer_mdot_kg_s": candidate["oxidizer_mdot_kg_s"],
        "initial_port_diameter_m": candidate["port_diameter_m"],
        "max_grain_od_in": cfg.GRAIN_MAX_OD_IN,
        "max_grain_od_m": cfg.GRAIN_MAX_OD_M,
        "grain_length_m": candidate["grain_length_m"],
        "sizing_initial_oxidizer_mass_kg": cfg.SIZING_INITIAL_OXIDIZER_MASS_KG,
    }


def result_to_record(
    case_id: int,
    mode: str,
    candidate: Dict[str, float],
    result,
) -> Dict[str, object]:
    record = _empty_record(case_id, mode, candidate)

    required_ox = result.oxidizer_consumed_kg
    burn_ok = cfg.BURN_TIME_MIN_S <= result.total_time <= cfg.BURN_TIME_MAX_S
    geometry_ok = cfg.GRAIN_LENGTH_MIN_M <= result.grain_length <= cfg.GRAIN_LENGTH_MAX_M
    tank_capacity_ok = required_ox <= result.model_tank_capacity_kg
    grain_burnout = result.final_port_diameter >= cfg.GRAIN_MAX_OD_M - 1e-9
    sizing_ox_depleted = result.final_ox_mass <= 1e-9

    record.update(
        {
            "required_initial_oxidizer_mass_kg": required_ox,
            "model_tank_capacity_kg": result.model_tank_capacity_kg,
            "nominal_26kg_fill_pass": required_ox <= 26.0,
            "burn_time_s": result.total_time,
            "total_impulse_Ns": result.total_impulse,
            "average_thrust_N": result.avg_thrust,
            "peak_thrust_N": max(result.thrust_curve),
            "average_isp_s": result.avg_isp,
            "average_of": result.avg_of,
            "initial_oxidizer_mass_flux_kg_m2_s": (
                candidate["oxidizer_mdot_kg_s"]
                / (0.25 * math.pi * candidate["port_diameter_m"] ** 2)
            ),
            "average_throat_mass_flux_kg_m2_s": (
                float(np.mean(result.throat_mass_flux))
                if result.throat_mass_flux
                else math.nan
            ),
            "final_oxidizer_mass_in_sizing_run_kg": result.final_ox_mass,
            "final_fuel_mass_kg": result.final_fuel_mass,
            "final_port_diameter_m": result.final_port_diameter,
            "raw_termination_reason": getattr(result, "termination_reason", "UNKNOWN"),
            "sizing_run_grain_burnout": grain_burnout,
            "sizing_run_oxidizer_depleted": sizing_ox_depleted,
            "burn_time_constraint_pass": burn_ok,
            "grain_length_constraint_pass": geometry_ok,
            "combustion_chamber_length_m": result.chamber_length_m,
            "cc_al_casing_mass_kg": result.cc_al_casing_mass_kg,
            "cc_chambersafe_mass_kg": result.cc_chambersafe_mass_kg,
            "cc_shell_mass_kg": result.cc_shell_mass_kg,
            "cc_dry_mass_kg": result.cc_dry_mass_kg,
            "upper_cc_cg_from_nozzle_exit_m": result.upper_cc_cg_m,
            "lower_cc_cg_from_nozzle_exit_m": result.lower_cc_cg_m,
            "tank_capacity_constraint_pass": tank_capacity_ok,
            "cea_mode": getattr(result, "cea_mode", "direct"),
            "cea_direct_calls": result.cea_stats["direct_calls"],
            "cea_new_grid_nodes": result.cea_stats["grid_nodes"],
            "cea_interpolations": result.cea_stats["interpolations"],
            "cea_direct_seconds": result.cea_stats["direct_seconds"],
            "cea_lookup_seconds": result.cea_stats["lookup_seconds"],
            "cea_total_seconds": result.cea_stats["direct_seconds"] + result.cea_stats["lookup_seconds"],
            "cea_failed_cells": result.cea_stats["failed_cells"],
            "feasible": bool(
                burn_ok and geometry_ok and tank_capacity_ok and grain_burnout
                and record["tank_pressure_constraint_pass"]
            ),
            "error": "",
        }
    )
    return record


def _write_outputs(mode: str, records: List[Dict[str, object]], bounds: Dict[str, Tuple[float, float]]) -> pd.DataFrame:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    all_path = RESULTS_DIR / f"{mode}_all.csv"
    df.to_csv(all_path, index=False)

    feasible = df[df["feasible"] == True].copy() if "feasible" in df.columns else pd.DataFrame()
    if not feasible.empty:
        feasible = feasible.sort_values("total_impulse_Ns", ascending=False).reset_index(drop=True)
        feasible.insert(0, "rank", np.arange(1, len(feasible) + 1))
    feasible.to_csv(RESULTS_DIR / f"{mode}_feasible.csv", index=False)

    top = feasible.head(cfg.TOP_CASES_FOR_FINE).copy()
    top.to_csv(RESULTS_DIR / f"{mode}_top{cfg.TOP_CASES_FOR_FINE}.csv", index=False)

    with open(RESULTS_DIR / f"{mode}_bounds.json", "w", encoding="utf-8") as f:
        json.dump({k: list(v) for k, v in bounds.items()}, f, indent=2)

    return feasible


def run_sweep(
    mode: str,
    case_count: int,
    bounds: Dict[str, Tuple[float, float]],
    seed: int,
    engine_module,
) -> pd.DataFrame:
    print(f"\n=== {mode.upper()} SWEEP: {case_count} geometry- and pressure-valid candidates ===")
    print("Bounds:")
    for name in VARIABLES:
        print(f"  {name}: {bounds[name][0]:.6g} .. {bounds[name][1]:.6g}")
    print(
        f"  requested Pc ceiling: {cfg.CHAMBER_PRESSURE_PSIG[1]:.2f} psig; "
        f"effective feasible ceiling: {EFFECTIVE_PC_MAX_PSIG:.3f} psig"
    )
    print(f"  fixed max grain OD: {cfg.GRAIN_MAX_OD_IN:.2f} in = {cfg.GRAIN_MAX_OD_M:.5f} m")
    print(f"  minimum injector stiffness: {cfg.MIN_INJECTOR_STIFFNESS:.4f}; maximum follows the tank cap at each Pc")
    print(f"  maximum initial tank pressure: {cfg.MAX_INITIAL_TANK_PRESSURE_PSIG:.2f} psig")
    if stiffness_interval(bounds, bounds["chamber_pressure_psig"][0]) is None:
        raise ValueError("No chamber pressure in the sweep range fits the tank-pressure limit.")
    print(
        f"  grain-length constraint: {cfg.GRAIN_LENGTH_MIN_M:.2f} .. "
        f"{cfg.GRAIN_LENGTH_MAX_M:.2f} m"
    )
    print(
        f"  burn-time constraint: {cfg.BURN_TIME_MIN_S:.1f} .. "
        f"{cfg.BURN_TIME_MAX_S:.1f} s"
    )

    candidates = generate_mode_candidates(mode, case_count, bounds, seed)
    records: List[Dict[str, object]] = []
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    simulations_run = 0
    feasible_count = 0
    if mode == "coarse":
        print(
            f"  adaptive coarse: at least {cfg.COARSE_MIN_CASES} cases; "
            f"stop after {cfg.COARSE_TARGET_FEASIBLE} feasible cases at a "
            f"{cfg.COARSE_CHECK_INTERVAL}-case boundary (maximum {case_count})"
        )
    else:
        print(f"  fine allocation: {sum(c['search_region'] == 'local' for c in candidates)} local, "
              f"{sum(c['search_region'] == 'global' for c in candidates)} global")

    try:
        for idx, candidate in enumerate(candidates, start=1):
            record = _empty_record(idx, mode, candidate)
            try:
                values = candidate_to_inputs(candidate, cfg.SIZING_INITIAL_OXIDIZER_MASS_KG)
                simulations_run += 1
                result = model_runner.run_case(values, engine_module=engine_module, quiet=True)
                record = result_to_record(idx, mode, candidate, result)
                status = "PASS" if record["feasible"] else "OUT"
                print(
                    f"[{idx:03d}/{case_count}] {status}  "
                    f"It={record['total_impulse_Ns']:.1f} Ns  "
                    f"tb={record['burn_time_s']:.3f} s  "
                    f"Pc={candidate['chamber_pressure_psig']:.1f} psi  "
                    f"Pt={record['tank_pressure_psig']:.1f} psi  "
                    f"S={candidate['injector_stiffness']:.3f}  "
                    f"region={candidate['search_region']}"
                )
            except Exception as exc:
                record.update(
                    {
                        "feasible": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"[{idx:03d}/{case_count}] ERROR  {record['error']}")

            records.append(record)
            feasible_count += bool(record["feasible"])
            if idx % cfg.CHECKPOINT_EVERY_CASES == 0:
                pd.DataFrame(records).to_csv(RESULTS_DIR / f"{mode}_all.csv", index=False)
            if mode == "coarse" and coarse_coverage_reached(idx, feasible_count):
                print(f"Coarse coverage target met: {feasible_count} feasible in {idx} cases.")
                break
    finally:
        # Ctrl+C keeps every completed case, including those since the last checkpoint.
        if records:
            pd.DataFrame(records).to_csv(RESULTS_DIR / f"{mode}_all.csv", index=False)

    feasible = _write_outputs(mode, records, bounds)
    elapsed = time.time() - start
    print(f"\n{mode.capitalize()} complete in {elapsed/60:.1f} min.")
    print(f"Simulated: {simulations_run} / {case_count} maximum; all generated candidates satisfy the initial tank-pressure limit.")
    complete = [r for r in records if "cea_direct_calls" in r]
    if complete:
        print(
            "CEA totals: "
            f"{sum(r['cea_direct_calls'] for r in complete)} direct calls, "
            f"{sum(r['cea_interpolations'] for r in complete)} interpolations, "
            f"{sum(r['cea_total_seconds'] for r in complete):.1f} s CEA+lookup"
        )
    print(f"Feasible: {len(feasible)} / {len(records)} completed")
    if not feasible.empty:
        best = feasible.iloc[0]
        print(
            "Best: "
            f"{best['total_impulse_Ns']:.1f} Ns, "
            f"burn {best['burn_time_s']:.3f} s, "
            f"Pc {best['chamber_pressure_psig']:.2f} psig, "
            f"tank {best['tank_pressure_psig']:.2f} psig, "
            f"S {best['injector_stiffness']:.4f}"
        )
        if mode == "fine" and best["search_region"] == "global":
            print("Review: best fine case came from the global reserve; the local fine box missed it.")
        elif mode == "fine":
            near_boundary = any(
                (float(best[column]) - bounds[name][0]) < 0.05 * (bounds[name][1] - bounds[name][0])
                or (bounds[name][1] - float(best[column])) < 0.05 * (bounds[name][1] - bounds[name][0])
                for name, column in (
                    ("chamber_pressure_psig", "chamber_pressure_psig"),
                    ("fuel_mass_kg", "initial_fuel_mass_kg"),
                    ("oxidizer_mdot_kg_s", "initial_oxidizer_mdot_kg_s"),
                    ("port_diameter_m", "initial_port_diameter_m"),
                    ("injector_stiffness", "injector_stiffness"),
                )
            )
            if near_boundary:
                print("Review: best fine case lies near a local search boundary; consider widening that bound.")
    print(f"Results: {RESULTS_DIR}")
    return feasible


def derive_fine_bounds(coarse_feasible: pd.DataFrame) -> Dict[str, Tuple[float, float]]:
    if coarse_feasible.empty:
        raise RuntimeError(
            "No feasible coarse cases were found, so a fine search region cannot be derived."
        )

    top = coarse_feasible.head(cfg.TOP_CASES_FOR_FINE)
    column_map = {
        "chamber_pressure_psig": "chamber_pressure_psig",
        "fuel_mass_kg": "initial_fuel_mass_kg",
        "oxidizer_mdot_kg_s": "initial_oxidizer_mdot_kg_s",
        "port_diameter_m": "initial_port_diameter_m",
        "injector_stiffness": "injector_stiffness",
    }
    fine: Dict[str, Tuple[float, float]] = {}

    for name in VARIABLES:
        global_lo, global_hi = GLOBAL_BOUNDS[name]
        global_span = global_hi - global_lo
        series = top[column_map[name]].astype(float)
        local_lo = float(series.min())
        local_hi = float(series.max())
        padding = cfg.FINE_PADDING_FRACTION * global_span

        lo = max(global_lo, local_lo - padding)
        hi = min(global_hi, local_hi + padding)

        # If top points collapse to a very narrow band, retain a useful window.
        min_width = 0.15 * global_span
        if hi - lo < min_width:
            center = 0.5 * (local_lo + local_hi)
            lo = max(global_lo, center - 0.5 * min_width)
            hi = min(global_hi, center + 0.5 * min_width)
            if hi - lo < min_width:
                if lo <= global_lo + 1e-12:
                    hi = min(global_hi, global_lo + min_width)
                elif hi >= global_hi - 1e-12:
                    lo = max(global_lo, global_hi - min_width)

        fine[name] = (lo, hi)

    return fine


def verify_top_with_sized_oxidizer(
    fine_feasible: pd.DataFrame,
    engine_module,
) -> pd.DataFrame:
    """Re-run the best fine cases using the derived required LOX mass.

    The sizing sweeps carry 26 kg only so oxidizer does not terminate the burn
    prematurely.  This verification run replaces 26 kg with the integrated LOX
    consumption from the sizing run and checks that oxidizer depletion and grain
    burnout coincide to within one time step worth of flow.
    """

    if fine_feasible.empty:
        return pd.DataFrame()

    verified_rows: List[Dict[str, object]] = []
    count = min(cfg.TOP_CASES_TO_VERIFY, len(fine_feasible))
    print(f"\nVerifying top {count} cases with sized initial oxidizer mass...")

    for i, (_, row) in enumerate(fine_feasible.head(count).iterrows(), start=1):
        candidate = {
            "chamber_pressure_psig": float(row["chamber_pressure_psig"]),
            "fuel_mass_kg": float(row["initial_fuel_mass_kg"]),
            "oxidizer_mdot_kg_s": float(row["initial_oxidizer_mdot_kg_s"]),
            "port_diameter_m": float(row["initial_port_diameter_m"]),
            "injector_stiffness": float(row["injector_stiffness"]),
            "grain_length_m": float(row["grain_length_m"]),
        }
        required_ox = float(row["required_initial_oxidizer_mass_kg"])
        output = row.to_dict()

        try:
            values = candidate_to_inputs(candidate, required_ox)
            result = model_runner.run_case(values, engine_module=engine_module, quiet=True)
            ox_tolerance = max(1e-6, 1.25 * result.final_ox_mdot * engine_module.TIME_STEP)
            grain_hit = result.final_port_diameter >= cfg.GRAIN_MAX_OD_M - 1e-9
            ox_hit = result.final_ox_mass <= ox_tolerance
            matched = bool(grain_hit and ox_hit)

            output.update(
                {
                    "verification_initial_oxidizer_mass_kg": required_ox,
                    "verification_final_oxidizer_mass_kg": result.final_ox_mass,
                    "verification_final_port_diameter_m": result.final_port_diameter,
                    "verification_burn_time_s": result.total_time,
                    "verification_total_impulse_Ns": result.total_impulse,
                    "verification_termination_reason": getattr(result, "termination_reason", "UNKNOWN"),
                    "burnout_and_oxidizer_depletion_matched": matched,
                    "verification_error": "",
                }
            )
            print(
                f"  #{i}: {'MATCH' if matched else 'CHECK'}  "
                f"LOX={required_ox:.4f} kg  final={result.final_ox_mass:.6f} kg"
            )
        except Exception as exc:
            output.update(
                {
                    "verification_initial_oxidizer_mass_kg": required_ox,
                    "burnout_and_oxidizer_depletion_matched": False,
                    "verification_error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"  #{i}: ERROR {output['verification_error']}")

        verified_rows.append(output)

    verified = pd.DataFrame(verified_rows)
    verified.to_csv(RESULTS_DIR / "fine_top10_verified.csv", index=False)
    if not verified.empty:
        matched = verified[verified["burnout_and_oxidizer_depletion_matched"] == True]
        best = matched.head(1) if not matched.empty else verified.head(1)
        best.to_csv(RESULTS_DIR / "best_design.csv", index=False)
    return verified


def load_coarse_feasible() -> pd.DataFrame:
    path = RESULTS_DIR / "coarse_feasible.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Run --mode coarse first (or use --mode all)."
        )
    coarse = pd.read_csv(path)
    if (
        "injector_stiffness" not in coarse.columns
        or "sweep_model_version" not in coarse.columns
        or "configuration_signature" not in coarse.columns
        or "minimum_injector_stiffness" not in coarse.columns
        or "max_initial_tank_pressure_psig" not in coarse.columns
        or coarse.empty
        or not coarse["sweep_model_version"].eq(cfg.SWEEP_MODEL_VERSION).all()
        or not coarse["configuration_signature"].eq(configuration_signature()).all()
        or not np.allclose(coarse["minimum_injector_stiffness"].astype(float), cfg.MIN_INJECTOR_STIFFNESS)
        or not np.allclose(coarse["max_initial_tank_pressure_psig"].astype(float), cfg.MAX_INITIAL_TANK_PRESSURE_PSIG)
    ):
        raise ValueError(
            "Existing coarse results used a different pressure rule or model version. "
            "Run --mode coarse again before running fine."
        )
    return coarse


def print_plan(mode: str, count: int, bounds: Dict[str, Tuple[float, float]], seed: int) -> None:
    candidates = generate_mode_candidates(mode, count, bounds, seed)
    df = pd.DataFrame(candidates)
    df["tank_pressure_psig"] = [
        model_runner.tank_pressure_psig_from_stiffness(pc, stiffness)
        for pc, stiffness in zip(df["chamber_pressure_psig"], df["injector_stiffness"])
    ]
    df["tank_pressure_constraint_pass"] = (
        df["tank_pressure_psig"] <= cfg.MAX_INITIAL_TANK_PRESSURE_PSIG
    )
    print(df.head(20).to_string(index=False))
    print(f"Injector stiffness: at least {cfg.MIN_INJECTOR_STIFFNESS:.4f}; upper bound from tank cap at each Pc")
    print(
        f"Pc: requested {cfg.CHAMBER_PRESSURE_PSIG[0]:.2f} .. "
        f"{cfg.CHAMBER_PRESSURE_PSIG[1]:.2f} psig; feasible ceiling "
        f"{EFFECTIVE_PC_MAX_PSIG:.3f} psig"
    )
    print(f"Maximum initial tank pressure: {cfg.MAX_INITIAL_TANK_PRESSURE_PSIG:.2f} psig")
    print(
        f"\nGenerated {len(df)} geometry- and pressure-valid candidates; "
        f"{int(df['tank_pressure_constraint_pass'].sum())} fit the tank-pressure cap. "
        "MATLAB was not started."
    )
    if mode == "coarse":
        print(f"Coarse can stop from {cfg.COARSE_MIN_CASES} cases after {cfg.COARSE_TARGET_FEASIBLE} feasible results; cap {count}.")
    else:
        print(f"Fine: {(df['search_region'] == 'local').sum()} local + {(df['search_region'] == 'global').sum()} global cases.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Coarse/Fine SweepRunner for the hybrid motor model")
    parser.add_argument(
        "--mode",
        choices=("coarse", "fine", "all"),
        required=True,
        help="coarse and fine use the case counts in sweep_config.py; all=both",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="generate/check the candidate plan without starting MATLAB",
    )
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.mode == "coarse" and args.plan_only:
        print_plan("coarse", cfg.COARSE_CASES, GLOBAL_BOUNDS, cfg.RANDOM_SEED)
        return 0

    if args.mode == "fine" and args.plan_only:
        coarse = load_coarse_feasible()
        fine_bounds = derive_fine_bounds(coarse)
        print_plan("fine", cfg.FINE_CASES, fine_bounds, cfg.RANDOM_SEED + 1000)
        return 0

    if args.mode == "all" and args.plan_only:
        print("Plan-only all mode can show the coarse plan only because fine bounds depend on coarse results.")
        print_plan("coarse", cfg.COARSE_CASES, GLOBAL_BOUNDS, cfg.RANDOM_SEED)
        return 0

    print("Starting/loading MATLAB once for the sweep process...")
    engine_module = model_runner.load_engine_module()

    coarse_feasible = None
    if args.mode in ("coarse", "all"):
        coarse_feasible = run_sweep(
            "coarse",
            cfg.COARSE_CASES,
            GLOBAL_BOUNDS,
            cfg.RANDOM_SEED,
            engine_module,
        )

    if args.mode in ("fine", "all"):
        if coarse_feasible is None:
            coarse_feasible = load_coarse_feasible()
        fine_bounds = derive_fine_bounds(coarse_feasible)
        with open(RESULTS_DIR / "fine_derived_bounds.json", "w", encoding="utf-8") as f:
            json.dump({k: list(v) for k, v in fine_bounds.items()}, f, indent=2)

        fine_feasible = run_sweep(
            "fine",
            cfg.FINE_CASES,
            fine_bounds,
            cfg.RANDOM_SEED + 1000,
            engine_module,
        )
        verify_top_with_sized_oxidizer(fine_feasible, engine_module)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nSweep interrupted. The current *_all.csv checkpoint has been retained.")
        raise SystemExit(130)
