# Hybrid Rocket Thrust Curve Generator UI
# This interface changes only user interaction and output handling.
# The underlying simulation equations, constants, and execution logic remain in the existing model modules.

from pathlib import Path
from datetime import datetime
import math
import re

import pandas as pd
import streamlit as st

import file_generator as fg
import mass_component
import model_runner
import input_settings
import cea_lookup_config


st.set_page_config(
    page_title="Hybrid Rocket Thrust Curve Generator",
    page_icon="🚀",
    layout="wide",
)


@st.cache_resource(show_spinner="Starting MATLAB and loading the engine model...")
def load_engine_module():
    # engine.py starts the MATLAB Engine when it is imported.
    # Streamlit caches the imported module so MATLAB is not restarted on every UI rerun.
    import engine
    return engine


ENGINE = load_engine_module()
PROJECT_DIR = Path(__file__).resolve().parent
RSE_DIR = PROJECT_DIR / "rse files"
BEST_DESIGN_PATH = PROJECT_DIR / "sweep_results" / "best_design.csv"


DEFAULTS = model_runner.get_default_inputs()
# Keep the UI default tied to the engine module's reference value.  SweepRunner
# separately fixes 5.75 in only inside sweep_config.py.
DEFAULTS["grain_max_od"] = ENGINE.GRAIN_MAX_OD
DEFAULT_STIFFNESS_PERCENT = 100.0 * model_runner.injector_stiffness_from_pressures(
    DEFAULTS["chamber_pressure"], DEFAULTS["target_press_psig"]
)
DEFAULTS["injector_stiffness_percent"] = DEFAULT_STIFFNESS_PERCENT
DEFAULTS["cea_mode"] = cea_lookup_config.MODE
try:
    DEFAULTS = input_settings.load_inputs(DEFAULTS)
except (OSError, ValueError, TypeError) as error:
    st.warning(f"Could not load previous inputs; using model defaults: {error}")
DEFAULT_STIFFNESS_PERCENT = DEFAULTS["injector_stiffness_percent"]



def build_inputs():
    st.subheader("Simulation Inputs")
    st.caption(
        "Inputs are restored from the last saved form, or from main.py defaults on first use. "
        "Run Simulation and Save Inputs both save these inputs to user_settings/last_inputs.json."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Motor**")
        ox_mass = st.number_input(
            "Initial oxidizer mass (kg)",
            min_value=0.0001,
            value=DEFAULTS["ox_mass"],
            format="%.6f",
            help="The oxidizer tank length is fixed at 1.1684 m; this input changes fill mass only.",
        )
        fuel_mass = st.number_input(
            "Initial fuel mass (kg)",
            min_value=0.0001,
            value=DEFAULTS["fuel_mass"],
            format="%.6f",
        )
        port_diameter = st.number_input(
            "Initial port diameter (m)",
            min_value=0.0001,
            value=DEFAULTS["port_diameter"],
            format="%.6f",
        )
        grain_max_od = st.number_input(
            "Maximum grain outer diameter (m)",
            min_value=0.0001,
            value=DEFAULTS["grain_max_od"],
            format="%.6f",
            help=(
                "Per-run GRAIN_MAX_OD. This value is used consistently for grain length, "
                "burnout, and chamber mass-per-length calculations."
            ),
        )
        ox_mdot = st.number_input(
            "Initial oxidizer mass flow rate (kg/s)",
            min_value=0.0001,
            value=DEFAULTS["ox_mdot"],
            format="%.6f",
        )
        expansion_ratio = st.number_input(
            "Nozzle expansion ratio",
            min_value=0.0001,
            value=DEFAULTS["expansion_ratio"],
            format="%.4f",
        )

    with col2:
        st.markdown("**Pressure System**")
        chamber_pressure = st.number_input(
            "Chamber pressure (psig)",
            min_value=0.0,
            value=DEFAULTS["chamber_pressure"],
            format="%.3f",
        )
        injector_stiffness_percent = st.number_input(
            "Injector stiffness: ΔP / chamber absolute pressure (%)",
            min_value=0.001,
            value=DEFAULT_STIFFNESS_PERCENT,
            format="%.3f",
            help="Design input. The tank pressure follows from the chamber pressure and this ratio.",
        )
        target_press_psig = model_runner.tank_pressure_psig_from_stiffness(
            chamber_pressure, injector_stiffness_percent / 100.0
        )
        st.text_input(
            "Calculated initial oxidizer tank pressure (psig)",
            value=f"{target_press_psig:.3f}",
            disabled=True,
        )
        press_temp = st.number_input(
            "Pressurant temperature (K)",
            min_value=1.0,
            value=DEFAULTS["press_temp"],
            format="%.3f",
        )
        copv_pressure_psig = st.number_input(
            "Initial COPV pressure (psig)",
            min_value=0.0,
            value=DEFAULTS["copv_pressure_psig"],
            format="%.3f",
        )
        copv_vol_l = st.number_input(
            "COPV volume (L)",
            min_value=0.0001,
            value=DEFAULTS["copv_vol_l"],
            format="%.4f",
        )

    with col3:
        st.markdown("**Vehicle / COPV**")
        min_thrust = st.number_input(
            "Minimum thrust setting (N)",
            min_value=0.0,
            value=DEFAULTS["min_thrust"],
            format="%.1f",
            help="This value is retained because it exists in the current main.py configuration.",
        )
        copv_length = st.number_input(
            "COPV length used by mass model (m)",
            min_value=0.0001,
            value=DEFAULTS["copv_length"],
            format="%.6f",
        )
        copv_dry_mass = st.number_input(
            "COPV dry mass (kg)",
            min_value=0.0001,
            value=DEFAULTS["copv_dry_mass"],
            format="%.6f",
        )
        st.text_input(
            "Oxidizer tank length (fixed)",
            value=f"{mass_component.FIXED_OX_TANK_LENGTH:.4f} m",
            disabled=True,
            help="Fixed flight-tank geometry; changing oxidizer mass does not resize the tank.",
        )

        st.markdown("**Current fixed selections**")
        st.text_input("Fuel", value=DEFAULTS["fuel_id"], disabled=True)
        st.text_input("Oxidizer", value=DEFAULTS["ox_id"], disabled=True)
        st.text_input("Pressurant", value=DEFAULTS["press_id"], disabled=True)

        cea_mode = st.selectbox(
            "CEA calculation",
            ["lookup", "direct"],
            index=["lookup", "direct"].index(DEFAULTS["cea_mode"]),
            help="Lookup stores CEA grid points on disk and validates interpolation against direct MATLAB CEA. Direct always calls MATLAB.",
        )

    with st.expander("Advanced mass-component inputs"):
        st.caption(
            "Defaults follow Copy of Combustion Devices Mass Calcs / Copy of Sheet3. "
            "Upper/lower chamber CG references follow the calculated grain and nozzle lengths. "
            "The middle Al casing and Chambersafe masses are calculated from grain length."
        )

        a, b, c = st.columns(3)
        with a:
            st.markdown("**Upper chamber**")
            upper_cc_mass = st.number_input(
                "Upper chamber mass (kg)",
                value=DEFAULTS["upper_cc_mass"],
                format="%.9f",
            )
            upper_cc_local_cg = st.number_input(
                "Upper chamber reference CG at nominal geometry (m)",
                value=DEFAULTS["upper_cc_local_cg"],
                format="%.9f",
                help=(
                    "Absolute position from the nozzle exit at the mass-sheet reference "
                    "geometry: 1.0434 m grain, 0.204597 m lower chamber, and 0.19 m nozzle. "
                    "The model moves this part when those lengths change."
                ),
            )
            upper_cc_length = st.number_input(
                "Upper chamber length (m)",
                value=DEFAULTS["upper_cc_length"],
                format="%.9f",
            )

            st.markdown("**Lower chamber**")
            lower_cc_mass = st.number_input(
                "Lower chamber mass (kg)",
                value=DEFAULTS["lower_cc_mass"],
                format="%.9f",
            )
            lower_cc_local_cg = st.number_input(
                "Lower chamber reference CG at nominal nozzle length (m)",
                value=DEFAULTS["lower_cc_local_cg"],
                format="%.9f",
                help="Absolute position from the nozzle exit with a 0.19 m reference nozzle; shifted if nozzle length changes.",
            )
            lower_cc_length = st.number_input(
                "Lower chamber length (m)",
                value=DEFAULTS["lower_cc_length"],
                format="%.9f",
            )

        with b:
            st.markdown("**Nozzle**")
            nozzle_mass = st.number_input(
                "Nozzle mass (kg)",
                value=DEFAULTS["nozzle_mass"],
                format="%.9f",
            )
            nozzle_local_cg = st.number_input(
                "Nozzle local CG (m)",
                value=DEFAULTS["nozzle_local_cg"],
                format="%.9f",
            )
            nozzle_length = st.number_input(
                "Nozzle length (m)",
                value=DEFAULTS["nozzle_length"],
                format="%.9f",
            )

            st.markdown("**CC-to-OX interstage**")
            interstage_cc_ox_mass = st.number_input(
                "CC-to-OX interstage mass (kg)",
                value=DEFAULTS["interstage_cc_ox_mass"],
                format="%.9f",
            )
            interstage_cc_ox_local_cg = st.number_input(
                "CC-to-OX interstage local CG (m)",
                value=DEFAULTS["interstage_cc_ox_local_cg"],
                format="%.9f",
            )
            interstage_cc_ox_length = st.number_input(
                "CC-to-OX interstage length (m)",
                value=DEFAULTS["interstage_cc_ox_length"],
                format="%.9f",
            )

        with c:
            st.markdown("**OX-to-COPV interstage**")
            interstage_ox_copv_mass = st.number_input(
                "OX-to-COPV interstage mass (kg)",
                value=DEFAULTS["interstage_ox_copv_mass"],
                format="%.9f",
            )
            interstage_ox_copv_local_cg = st.number_input(
                "OX-to-COPV interstage local CG (m)",
                value=DEFAULTS["interstage_ox_copv_local_cg"],
                format="%.9f",
            )
            interstage_ox_copv_length = st.number_input(
                "OX-to-COPV interstage length (m)",
                value=DEFAULTS["interstage_ox_copv_length"],
                format="%.9f",
            )

    return {
        "min_thrust": min_thrust,
        "chamber_pressure": chamber_pressure,
        "injector_stiffness_percent": injector_stiffness_percent,
        "cea_mode": cea_mode,
        "copv_length": copv_length,
        "copv_dry_mass": copv_dry_mass,
        "fuel_id": DEFAULTS["fuel_id"],
        "ox_id": DEFAULTS["ox_id"],
        "press_id": DEFAULTS["press_id"],
        "ox_pvap_psi": DEFAULTS["ox_pvap_psi"],
        "ox_mass": ox_mass,
        "fuel_mass": fuel_mass,
        "port_diameter": port_diameter,
        "grain_max_od": grain_max_od,
        "ox_mdot": ox_mdot,
        "expansion_ratio": expansion_ratio,
        "target_press_psig": target_press_psig,
        "press_temp": press_temp,
        "copv_pressure_psig": copv_pressure_psig,
        "copv_vol_l": copv_vol_l,
        "upper_cc_mass": upper_cc_mass,
        "upper_cc_local_cg": upper_cc_local_cg,
        "upper_cc_length": upper_cc_length,
        "lower_cc_mass": lower_cc_mass,
        "lower_cc_local_cg": lower_cc_local_cg,
        "lower_cc_length": lower_cc_length,
        "nozzle_mass": nozzle_mass,
        "nozzle_local_cg": nozzle_local_cg,
        "nozzle_length": nozzle_length,
        "interstage_cc_ox_mass": interstage_cc_ox_mass,
        "interstage_cc_ox_local_cg": interstage_cc_ox_local_cg,
        "interstage_cc_ox_length": interstage_cc_ox_length,
        "interstage_ox_copv_mass": interstage_ox_copv_mass,
        "interstage_ox_copv_local_cg": interstage_ox_copv_local_cg,
        "interstage_ox_copv_length": interstage_ox_copv_length,
    }


def validate_inputs(values):
    errors = []

    if values["target_press_psig"] <= values["chamber_pressure"]:
        errors.append(
            "Initial oxidizer tank pressure must be greater than chamber pressure "
            "for the current injector equation."
        )

    if values["grain_max_od"] >= ENGINE.CC_ID:
        errors.append(
            f"Maximum grain OD must be smaller than the chamber ID ({ENGINE.CC_ID:.6f} m)."
        )

    if values["port_diameter"] >= values["grain_max_od"]:
        errors.append(
            "Initial port diameter must be smaller than the selected maximum grain outer diameter "
            "to produce a positive fuel-grain cross-sectional area."
        )

    return errors


def run_simulation(values):
    # Streamlit and SweepRunner now call the same programmatic model interface.
    # The UI and sweep each supply their own stiffness design value.
    # The sweep-only 5.75-in grain OD is not applied here.
    return model_runner.run_case(values, engine_module=ENGINE, quiet=False)


def print_legacy_terminal_output(result):
    """Print the same engine-result variables as the pre-UI main.py.

    This intentionally mirrors the legacy ``engine_result.print_parameters``
    text output, but does not call ``disp_graphs()`` because Streamlit renders
    the plots in the browser.  No additional UI/SweepRunner-only fields are
    printed here.
    """
    print (" *** INITIAL CONDITIONS *** " )
    print ("Initial Oxidizer Mass: " + str (round (result.init_ox_mass, 4)) + " kg")
    print ("Initial Fuel Mass: " + str (round (result.init_fuel_mass, 4)) + " kg")
    print ("Initial Pressurant Mass: " + str (round (result.init_press_mass, 4)) + " kg")
    print ("     ---------------- " )
    print (" *** FINAL CONDITIONS ***")
    print ("Remaining Oxidizer: " + str (round (result.final_ox_mass, 4)) + " kg")
    print ("Remaining Fuel: " + str (round (result.final_fuel_mass, 4)) + " kg")
    print ("Final Port Diameter: " + str (round (result.final_port_diameter, 4)) + " m")
    print ("     ------------------ " )
    print (" *** OX CONDITIONS *** " )
    print ("Ox Tank Length: " + str (round (result.tank_length, 4)) + " m")
    print ("Ox Mass Flow Rate: " + str (round (result.init_ox_mdot, 4)) + " kg/s")
    print ("     ------------------ " )
    print (" *** CHAMBER CONDITIONS *** " )
    print ("Grain Length: " + str (round (result.grain_length, 4)) + " m")
    print ("Initial Port Diameter: " + str (round (result.init_port_diameter, 4)) + " m")
    print ("Max Port Mass Flux: " + str (round (result.init_ox_mdot/(0.25*math.pi*result.init_port_diameter**2), 4)) + " kg/m^2")
    print ("Chamber Temperature: " + str (round(result.Tc, 4)) + " K")
    print ("Throat Temperature: " + str (round(result.Tt, 4)) + " K")
    print ("Exit Temperature: " + str (round (result.Te, 4)) + " K")
    print ("     ----------- " )
    print (" *** NOZZLE CONDITIONS *** " )
    print ("Throat Diameter: " + str (round (result.throatDia, 4)) + " mm")
    print ("Exit Diameter: " + str (round (result.exitDia, 4)) + " mm")
    print ("Average Throat Mass Flux: " + str (round (sum(result.throat_mass_flux)/len(result.throat_mass_flux), 4)) + " kg/m^2")
    print ("Expansion Ratio: " + str (round (result.expansion_ratio, 4)))
    print ("     ----------- " )
    print (" *** PERFORMANCE ***")
    print ("Average Thrust: " + str (round (result.avg_thrust, 4)) + " N")
    print ("Max Thrust (N): " + str (round (max (result.thrust_curve), 4)) + " N")
    print ("Max Thrust (lbf): " + str (round (model_runner.UNIT.N_to_lbf (max (result.thrust_curve)), 4)) + " lbf")
    print ("Burn Time: " + str (round (result.total_time, 4)) + " s")
    print ("Average Thrust Coefficient: " + str (round (result.avg_coef, 4)))
    print ("Total Impulse: " + str (round (result.total_impulse, 4)) + " Ns")
    print ("Average ISP: " + str (round (result.avg_isp, 4)) + " s")


def get_rse_code(result):
    impulse = result.total_impulse

    if 10240 > impulse >= 5120.01:
        prefix = "M"
    elif 20480 > impulse >= 10240.01:
        prefix = "N"
    elif 40960 > impulse >= 20480.01:
        prefix = "O"
    elif 81920 > impulse >= 40960.01:
        prefix = "P"
    elif 163840 > impulse >= 81920.01:
        prefix = "Q"
    elif 327680 > impulse >= 163840.01:
        prefix = "R"
    elif 655360 > impulse >= 327680.01:
        prefix = "S"
    else:
        return None

    return f"{prefix}-{int(round(result.avg_thrust, 4))}"


def generate_rse(result):
    diam = round(result.diam, 4)
    length = round(result.length, 4)
    init_wt = round(result.initWt, 4)
    prop_wt = round(result.propWt, 4)
    avg_thrust = round(result.avg_thrust, 4)
    peak_thrust = round(max(result.thrust_curve), 4)
    throat_dia = round(result.throatDia, 4)
    exit_dia = round(result.exitDia, 4)
    total_impulse = round(result.total_impulse, 4)
    burn_time = round(result.total_time, 4)
    mass_frac = round(result.massFrac, 4)
    avg_isp = round(result.avg_isp, 4)

    fg.rse_file(
        result.time,
        result.thrust_curve,
        result.m_curve,
        result.cg_curve,
        diam,
        length,
        init_wt,
        prop_wt,
        0,
        0,
        0,
        avg_thrust,
        peak_thrust,
        throat_dia,
        exit_dia,
        total_impulse,
        burn_time,
        mass_frac,
        avg_isp,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )

    code = get_rse_code(result)
    if code is None:
        return None

    return RSE_DIR / f"{code}_columbia-hybrid.rse"


def save_best_design_copy(source_path, archive_name):
    """Save the current sweep winner under a new name without overwriting it."""
    name = archive_name.strip()
    if name.lower().endswith(".csv"):
        name = name[:-4]

    # The project is normally run on Windows. Keep user-chosen names safe on
    # both Windows and other operating systems, including Japanese names.
    if (
        not name
        or name in {".", ".."}
        or name[-1] in {" ", "."}
        or re.search(r'[\\/:*?"<>|\x00-\x1f]', name)
        or name.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
    ):
        raise ValueError("Enter a valid filename without a path or special characters.")

    source_path = Path(source_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Sweep result not found: {source_path}")

    destination_dir = source_path.parent / "saved_designs"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{name}.csv"

    # The sweep result is a small, single-row CSV. Read it before creating the
    # destination so a missing source cannot leave an empty saved file.
    contents = source_path.read_bytes()
    created = False
    try:
        # Exclusive creation protects previous snapshots, including two clicks
        # from separate browser sessions using the same filename.
        with destination.open("xb") as output:
            created = True
            output.write(contents)
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise

    return destination


def show_results(result):
    st.subheader("Simulation Results")

    metric_rows = [
        (
            ("Average thrust", f"{result.avg_thrust:,.1f} N"),
            ("Peak thrust", f"{max(result.thrust_curve):,.1f} N"),
            ("Total impulse", f"{result.total_impulse:,.1f} N·s"),
            ("Burn time", f"{result.total_time:,.3f} s"),
        ),
        (
            ("Average ISP", f"{result.avg_isp:,.2f} s"),
            ("Average O/F", f"{result.avg_of:,.3f}" if result.avg_of is not None else "N/A"),
            ("Grain length", f"{result.grain_length:,.4f} m"),
            ("Tank length", f"{result.tank_length:,.4f} m"),
        ),
    ]

    for row in metric_rows:
        cols = st.columns(4)
        for col, (label, value) in zip(cols, row):
            col.metric(label, value)

    time = pd.Series(result.time, name="Time (s)")

    thrust_df = pd.DataFrame(
        {
            "Time (s)": time,
            "Thrust (N)": result.thrust_curve,
        }
    ).set_index("Time (s)")

    of_df = pd.DataFrame(
        {
            "Time (s)": time,
            "O/F Ratio": result.of_curve,
        }
    ).set_index("Time (s)")

    mass_df = pd.DataFrame(
        {
            "Time (s)": time,
            "Wet mass (kg)": [value / 1000.0 for value in result.m_curve],
        }
    ).set_index("Time (s)")

    cg_df = pd.DataFrame(
        {
            "Time (s)": time,
            "CG (m)": [value / 1000.0 for value in result.cg_curve],
        }
    ).set_index("Time (s)")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["Thrust", "O/F", "Mass", "CG", "Weight breakdown", "Detailed values"]
    )

    with tab1:
        st.line_chart(thrust_df, height=420)

    with tab2:
        st.line_chart(of_df, height=420)

    with tab3:
        st.line_chart(mass_df, height=420)

    with tab4:
        st.line_chart(cg_df, height=420)

    with tab5:
        st.caption(
            "Upper/lower chamber defaults and middle section reference masses follow Copy of Sheet3. "
            "The Al casing's 5.437 kg reference differs from its displayed-diameter calculation; the model keeps that reference and uses the displayed diameters for length changes. "
            "The nozzle exit is x=0. LOX CG follows its liquid column; N2 remains at the COPV center."
        )
        for label, rows, reference_cg, reference_mass in (
            ("Initial", result.initial_mass_breakdown, result.cg_curve[0] / 1000.0, result.m_curve[0] / 1000.0),
            ("Final", result.final_mass_breakdown,
             result.final_breakdown_cg_m, result.final_breakdown_mass_kg),
        ):
            st.markdown(f"**{label}**")
            frame = pd.DataFrame(rows)
            mass = frame["Mass (kg)"].sum()
            moment = frame["Moment (kg m)"].sum()
            cg = moment / mass
            dry = frame.loc[frame["Type"] == "Dry", "Mass (kg)"].sum()
            st.dataframe(frame, width="stretch", hide_index=True)
            st.write(f"Dry: {dry:.4f} kg · Wet: {mass:.4f} kg · Moment: {moment:.4f} kg·m · CG: {cg:.4f} m")
            if abs(mass - reference_mass) > 1e-7 or abs(cg - reference_cg) > 1e-7:
                st.warning("Component totals differ from the simulation mass/CG; check the model inputs.")
        st.caption("The final table uses remaining propellants; the model holds N2 mass and CG at its initial COPV value.")

    with tab6:
        details = {
            "Initial oxidizer mass (kg)": result.init_ox_mass,
            "Final oxidizer mass (kg)": result.final_ox_mass,
            "Oxidizer consumed (kg)": getattr(result, "oxidizer_consumed_kg", result.init_ox_mass - result.final_ox_mass),
            "Termination reason": getattr(result, "termination_reason", "UNKNOWN"),
            "Initial fuel mass (kg)": result.init_fuel_mass,
            "Final fuel mass (kg)": result.final_fuel_mass,
            "Initial pressurant mass (kg)": result.init_press_mass,
            "Initial port diameter (m)": result.init_port_diameter,
            "Maximum grain outer diameter (m)": getattr(result, "grain_max_od", math.nan),
            "Combustion chamber length (m)": result.chamber_length_m,
            "Al casing mass in grain section (kg)": result.cc_al_casing_mass_kg,
            "Chambersafe mass in grain section (kg)": result.cc_chambersafe_mass_kg,
            "Total chamber shell mass (kg)": result.cc_shell_mass_kg,
            "Total chamber dry mass including nozzle (kg)": result.cc_dry_mass_kg,
            "Upper chamber CG from nozzle exit (m)": result.upper_cc_cg_m,
            "Lower chamber CG from nozzle exit (m)": result.lower_cc_cg_m,
            "Final port diameter (m)": result.final_port_diameter,
            "Initial oxidizer mass flow rate (kg/s)": result.init_ox_mdot,
            "Design injector stiffness (%)": 100.0 * result.injector_stiffness_setting,
            "Calculated initial oxidizer tank pressure (psig)": result.tank_pressure_setting_psig,
            "Final oxidizer mass flow rate (kg/s)": result.final_ox_mdot,
            "Expansion ratio": result.expansion_ratio,
            "Chamber temperature (K)": result.Tc,
            "Throat temperature (K)": result.Tt,
            "Exit temperature (K)": result.Te,
            "Throat diameter (mm)": result.throatDia,
            "Exit diameter (mm)": result.exitDia,
            "Average thrust coefficient": result.avg_coef,
            "Propellant mass fraction (%)": result.massFrac,
            "Average throat mass flux (kg/m²)": (
                sum(result.throat_mass_flux) / len(result.throat_mass_flux)
                if result.throat_mass_flux
                else math.nan
            ),
        }
        stats = getattr(result, "cea_stats", {})
        details.update({
            "CEA mode": getattr(result, "cea_mode", "direct"),
            "Direct MATLAB CEA calls": stats.get("direct_calls", 0),
            "CEA grid nodes newly saved": stats.get("grid_nodes", 0),
            "CEA interpolated calls": stats.get("interpolations", 0),
            "CEA cells validated": stats.get("verified_cells", 0),
            "CEA cells rejected": stats.get("failed_cells", 0),
            "Direct CEA time (s)": stats.get("direct_seconds", 0.0),
            "Lookup overhead (s)": stats.get("lookup_seconds", 0.0),
            "Total CEA and lookup time (s)": stats.get("direct_seconds", 0.0) + stats.get("lookup_seconds", 0.0),
        })

        detail_df = pd.DataFrame(
            [{"Parameter": str(key), "Value": str(value)} for key, value in details.items()]
        )
        st.dataframe(detail_df, width="stretch", hide_index=True)


st.title("Hybrid Rocket Thrust Curve Generator")
st.caption(
    "Run the existing hybrid-motor model without editing Python. "
    "RSE export is intentionally separate from simulation execution."
)

with st.expander("Current model constants", expanded=False):
    constants = pd.DataFrame(
        [
            ("Fuel", str(DEFAULTS["fuel_id"])),
            ("Oxidizer", str(DEFAULTS["ox_id"])),
            ("Pressurant", str(DEFAULTS["press_id"])),
            ("Simulation time step", f"{ENGINE.TIME_STEP} s"),
            ("CEA update interval", f"{ENGINE.LOOPS_PER_CEA_ITERATION} loops"),
            ("C-star efficiency", str(ENGINE.CSTAR_EFFICIENCY)),
            ("Nozzle discharge coefficient", str(ENGINE.NOZZLE_DISCHARGE_COEFFICIENT)),
            ("Injector discharge coefficient", str(ENGINE.INJECTOR_DISCHARGE_COEFFICIENT)),
            ("Default maximum grain OD", f"{ENGINE.GRAIN_MAX_OD} m (editable in Motor inputs)"),
            ("Oxidizer tank length", f"{mass_component.FIXED_OX_TANK_LENGTH} m (fixed)"),
        ],
        columns=["Model item", "Current value"],
    )
    st.dataframe(constants, width="stretch", hide_index=True)

with st.form("simulation_form"):
    values = build_inputs()
    save_clicked = st.form_submit_button("Save Inputs")
    run_clicked = st.form_submit_button(
        "Run Simulation",
        type="primary",
        width="stretch",
    )

if save_clicked or run_clicked:
    try:
        saved_path = input_settings.save_inputs(values)
        if save_clicked:
            st.success(f"Inputs saved: {saved_path}")
    except OSError as exc:
        st.error(f"Could not save inputs: {exc}")

if run_clicked:
    errors = validate_inputs(values)

    if errors:
        for error in errors:
            st.error(error)
    else:
        try:
            with st.spinner("Running simulation with the current model..."):
                result = run_simulation(values)

            # Restore the pre-UI terminal report: same variables and labels as
            # legacy engine_result.print_parameters(), without opening matplotlib windows.
            print_legacy_terminal_output(result)

            st.session_state["simulation_result"] = result
            st.session_state["simulation_inputs"] = values
            st.session_state.pop("last_rse_path", None)
            st.success(
                "Simulation completed. No RSE file has been created. "
                "Use the export button below only when you want an output file."
            )
        except Exception as exc:
            st.session_state.pop("simulation_result", None)
            st.error("Simulation failed.")
            st.exception(exc)

result = st.session_state.get("simulation_result")

if result is not None:
    show_results(result)

    st.divider()
    st.subheader("RSE Export")
    st.caption(
        "This action uses the existing file_generator.py logic and writes the file "
        "to the project's 'rse files' folder."
    )

    code = get_rse_code(result)
    if code is None:
        st.warning(
            "The current total impulse is outside the impulse ranges supported by "
            "the existing RSE generator, so an RSE file cannot be generated."
        )
    else:
        expected_path = RSE_DIR / f"{code}_columbia-hybrid.rse"
        st.write(f"Expected output: `{expected_path}`")

        if st.button("Generate RSE File", width="stretch"):
            existed_before = expected_path.exists()

            try:
                output_path = generate_rse(result)
                st.session_state["last_rse_path"] = str(output_path)

                if existed_before:
                    st.warning("An existing RSE file with the same motor code was overwritten.")

                st.success(f"RSE file created: {output_path}")
            except Exception as exc:
                st.error("RSE generation failed.")
                st.exception(exc)

    last_rse_path = st.session_state.get("last_rse_path")
    if last_rse_path:
        st.info(f"Last generated RSE file: {last_rse_path}")
else:
    st.info("Set the inputs above and click Run Simulation to begin.")

st.divider()
st.subheader("Save Sweep Best Design")
if BEST_DESIGN_PATH.is_file():
    st.caption(
        "Save a separate copy of the current sweep_results/best_design.csv. "
        "The next sweep can update best_design.csv without changing this copy."
    )
    if "best_design_archive_name" not in st.session_state:
        st.session_state["best_design_archive_name"] = (
            "best_design_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        )
    archive_name = st.text_input(
        "Copy filename (.csv)",
        key="best_design_archive_name",
    )
    if st.button("Save Best Design As...", width="stretch"):
        try:
            saved_path = save_best_design_copy(BEST_DESIGN_PATH, archive_name)
        except FileExistsError:
            st.error("A saved design already has that name. Choose another filename.")
        except (OSError, ValueError) as exc:
            st.error(f"Could not save the design: {exc}")
        else:
            st.success(f"Saved: {saved_path}")
else:
    st.info("Run SweepRunner first to create sweep_results/best_design.csv.")
