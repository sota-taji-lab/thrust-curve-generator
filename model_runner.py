"""Shared programmatic interface for the hybrid-rocket model.

This module contains no Streamlit UI code.  Both ``streamlit_app.py`` and
``sweep_runner.py`` can call the same ``run_case`` function so that a sweep is
not a browser/UI automation layer; it is a second controller for the same
engine model.
"""

from __future__ import annotations

import contextlib
import math
import os
from copy import deepcopy
from typing import Any, Dict, Optional

import mass_component
import unit_converter as unit


UNIT = unit.unit()

# These reproduce the current Streamlit/main configuration.  Sweep-specific
# coupling and fixed values live in sweep_config.py and do not change the UI.
BASE_INPUTS: Dict[str, Any] = {
    "min_thrust": 8000.0,
    "chamber_pressure": 300.0,
    "copv_length": 0.47,
    "copv_dry_mass": 3.9,
    "fuel_id": "PARAFFIN",
    "ox_id": "LOX",
    "press_id": "Nitrogen",
    "ox_pvap_psi": 0.0,
    "ox_mass": 30.0 - 0.723 - 5.8799,
    "fuel_mass": 10.8,
    "port_diameter": 0.101,
    "grain_max_od": 0.14605,
    "ox_mdot": 2.31,
    "expansion_ratio": 4.5,
    "target_press_psig": 418.0,
    "press_temp": 320.0,
    "copv_pressure_psig": 4350.0,
    "copv_vol_l": 6.8,
    "upper_cc_mass": 1.180667826,
    "upper_cc_local_cg": 1.480748896,
    "upper_cc_length": 0.07112,
    "lower_cc_mass": 2.662613559,
    "lower_cc_local_cg": 0.2850052543,
    "lower_cc_length": 0.204597,
    "nozzle_mass": 3.897,
    "nozzle_local_cg": 0.1209618424,
    "nozzle_length": 0.19,
    "interstage_cc_ox_mass": 4.389,
    "interstage_cc_ox_local_cg": 0.07192547133,
    "interstage_cc_ox_length": 0.231124,
    "interstage_ox_copv_mass": 7.627,
    "interstage_ox_copv_local_cg": 0.2046026227,
    "interstage_ox_copv_length": 0.310007,
}


def get_default_inputs() -> Dict[str, Any]:
    """Return an independent copy of the baseline model inputs."""

    return deepcopy(BASE_INPUTS)


def tank_pressure_psig_from_stiffness(chamber_pressure_psig: float, stiffness: float) -> float:
    """Return tank gauge pressure for stiffness = (Ptank - Pc) / Pc(abs)."""
    chamber_pressure_pa = UNIT.psig_To_Pa(chamber_pressure_psig)
    if not math.isfinite(chamber_pressure_pa) or chamber_pressure_pa <= 0:
        raise ValueError("Chamber absolute pressure must be positive.")
    if not math.isfinite(stiffness) or stiffness <= 0:
        raise ValueError("Injector stiffness must be positive and finite.")
    return UNIT.Pa_to_psig(chamber_pressure_pa * (1.0 + stiffness))


def injector_stiffness_from_pressures(chamber_pressure_psig: float, tank_pressure_psig: float) -> float:
    """Return the initial injector pressure-drop ratio using chamber absolute pressure."""
    chamber_pressure_pa = UNIT.psig_To_Pa(chamber_pressure_psig)
    tank_pressure_pa = UNIT.psig_To_Pa(tank_pressure_psig)
    if not math.isfinite(chamber_pressure_pa) or chamber_pressure_pa <= 0:
        raise ValueError("Chamber absolute pressure must be positive.")
    if not math.isfinite(tank_pressure_pa) or tank_pressure_pa <= chamber_pressure_pa:
        raise ValueError("Tank pressure must be greater than chamber pressure.")
    return (tank_pressure_pa - chamber_pressure_pa) / chamber_pressure_pa


def max_chamber_pressure_psig(tank_pressure_cap_psig: float, minimum_stiffness: float) -> float:
    """Highest chamber gauge pressure compatible with a tank cap and S minimum."""
    if not math.isfinite(minimum_stiffness) or minimum_stiffness <= 0:
        raise ValueError("Minimum injector stiffness must be positive and finite.")
    tank_pa = UNIT.psig_To_Pa(tank_pressure_cap_psig)
    if not math.isfinite(tank_pa) or tank_pa <= 0:
        raise ValueError("Tank pressure cap must be positive and finite.")
    return UNIT.Pa_to_psig(tank_pa / (1.0 + minimum_stiffness))


def load_engine_module():
    """Import engine.py lazily.

    Importing engine.py starts MATLAB.  Keeping this lazy lets geometry-only
    checks and sweep planning run without starting MATLAB.
    """

    import engine

    return engine


def validate_case(values: Dict[str, Any], engine_module=None) -> list[str]:
    """Validate only model-level relationships shared by UI and sweep."""

    errors: list[str] = []
    cc_id = 0.15875 if engine_module is None else engine_module.CC_ID

    if values["target_press_psig"] <= values["chamber_pressure"]:
        errors.append(
            "Initial oxidizer tank pressure must be greater than chamber pressure "
            "for the current injector equation."
        )

    if values["grain_max_od"] >= cc_id:
        errors.append(
            f"Maximum grain OD must be smaller than the chamber ID ({cc_id:.6f} m)."
        )

    if values["port_diameter"] >= values["grain_max_od"]:
        errors.append(
            "Initial port diameter must be smaller than the selected maximum grain outer diameter."
        )

    return errors


def calculate_grain_length_m(
    fuel_mass_kg: float,
    port_diameter_m: float,
    grain_outer_diameter_m: float,
    fuel_density_kg_m3: float = 900.0,
) -> float:
    """Return cylindrical annular grain length used by the current model."""

    area = 0.25 * 3.141592653589793 * (
        grain_outer_diameter_m**2 - port_diameter_m**2
    )
    if area <= 0:
        raise ValueError("Fuel-grain cross-sectional area must be positive.")
    return fuel_mass_kg / (fuel_density_kg_m3 * area)


def run_case(
    values: Dict[str, Any],
    *,
    engine_module=None,
    quiet: bool = False,
):
    """Run one case through the existing engine model and return engine_result.

    ``engine_module`` may be supplied so a sweep can start MATLAB once and reuse
    the same imported module for all cases.
    """

    if engine_module is None:
        engine_module = load_engine_module()

    errors = validate_case(values, engine_module=engine_module)
    if errors:
        raise ValueError("; ".join(errors))

    import CoolProp.CoolProp as cp
    import engine_parameter as eng_param

    target_press_pa = UNIT.psig_To_Pa(values["target_press_psig"])
    copv_vol = values["copv_vol_l"] / 1000.0

    init_press_mass = copv_vol * cp.PropsSI(
        "D",
        "P|gas",
        UNIT.psig_To_Pa(values["copv_pressure_psig"]),
        "T",
        values["press_temp"],
        values["press_id"],
    )

    motor = engine_module.engine(
        values["min_thrust"],
        values["chamber_pressure"],
        values["fuel_id"],
        values["ox_id"],
        values["press_id"],
        UNIT.psig_To_Pa(values["ox_pvap_psi"]),
        values["grain_max_od"],
    )
    if "cea_mode" in values:
        if values["cea_mode"] not in ("lookup", "direct"):
            raise ValueError("CEA mode must be lookup or direct")
        motor.cea_evaluator.mode = values["cea_mode"]

    simulation_input = eng_param.engine_parameter(
        values["ox_mass"],
        values["fuel_mass"],
        values["port_diameter"],
        values["ox_mdot"],
        values["expansion_ratio"],
        init_press_mass,
    )

    upper_cc = mass_component.part(
        values["upper_cc_mass"],
        values["upper_cc_local_cg"],
        values["upper_cc_length"],
        "ABS",
    )
    lower_cc = mass_component.part(
        values["lower_cc_mass"],
        values["lower_cc_local_cg"],
        values["lower_cc_length"],
        "ABS",
    )
    nozzle = mass_component.part(
        values["nozzle_mass"],
        values["nozzle_local_cg"],
        values["nozzle_length"],
        "ABS",
    )
    interstage_cc_ox = mass_component.part(
        values["interstage_cc_ox_mass"],
        values["interstage_cc_ox_local_cg"],
        values["interstage_cc_ox_length"],
        "CC",
    )
    interstage_ox_copv = mass_component.part(
        values["interstage_ox_copv_mass"],
        values["interstage_ox_copv_local_cg"],
        values["interstage_ox_copv_length"],
        "OX",
    )

    def _execute():
        return motor.run_simulation(
            simulation_input,
            target_press_pa,
            values["copv_length"],
            values["copv_dry_mass"],
            copv_vol,
            lower_cc,
            upper_cc,
            nozzle,
            interstage_cc_ox,
            interstage_ox_copv,
        )

    try:
        if quiet:
            # The legacy model prints every time step.  Sweeps would otherwise flood
            # the terminal; discard those prints while leaving exceptions visible.
            with open(os.devnull, "w", encoding="utf-8") as devnull:
                with contextlib.redirect_stdout(devnull):
                    result = _execute()
        else:
            result = _execute()
    finally:
        motor.cea_evaluator.close()

    # Attach a few controller-level fields without altering the model equations.
    tank_volume_m3 = (
        mass_component.FIXED_OX_TANK_LENGTH
        * 0.25
        * 3.141592653589793
        * engine_module.TANK_ID**2
    )
    result.model_tank_capacity_kg = tank_volume_m3 * motor.ox_density
    result.chamber_pressure_setting_psig = values["chamber_pressure"]
    result.tank_pressure_setting_psig = values["target_press_psig"]
    result.chamber_length_m = motor.thisMoc.cc_length
    result.cc_al_casing_mass_kg = motor.thisMoc.cc_al_mass
    result.cc_chambersafe_mass_kg = motor.thisMoc.cc_cs_mass
    result.cc_shell_mass_kg = motor.thisMoc.cc_shell_mass
    result.cc_dry_mass_kg = motor.thisMoc.cc_mass
    result.upper_cc_cg_m = motor.thisMoc.upper_cc_cg_abs
    result.lower_cc_cg_m = motor.thisMoc.lower_cc_cg_abs
    result.injector_stiffness_setting = injector_stiffness_from_pressures(
        values["chamber_pressure"], values["target_press_psig"]
    )
    result.oxidizer_consumed_kg = result.init_ox_mass - result.final_ox_mass

    if not quiet:
        components = motor.thisMoc
        result.initial_mass_breakdown = components.mass_breakdown(
            result.init_ox_mass, result.init_fuel_mass, result.init_press_mass
        )
        # Pressurant transfer to the oxidizer tank is explicitly out of scope.
        result.final_mass_breakdown = components.mass_breakdown(
            result.final_ox_mass, result.final_fuel_mass, result.init_press_mass
        )
        result.final_breakdown_cg_m, result.final_breakdown_mass_kg = components.current_cg_wet_mass(
            result.final_ox_mass, result.final_fuel_mass, result.init_press_mass
        )

    return result
