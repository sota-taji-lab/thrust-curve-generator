"""Configuration for an exploratory 2.3 kg/s initial-LOX-flow SweepRunner.

Only the external sweep controller uses this file. Streamlit has its own
injector-stiffness input and editable maximum grain OD.
The flow range below constrains initial LOX flow, not its peak during a burn.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Sweep sizes
# ---------------------------------------------------------------------------
COARSE_CASES = 1200
COARSE_MIN_CASES = 1200  # Complete the broad search before refinement.
COARSE_TARGET_FEASIBLE = 30  # No early exit when minimum equals the cap.
COARSE_CHECK_INTERVAL = 100
FINE_CASES = 600
FINE_GLOBAL_FRACTION = 0.15  # 90 broad, 510 in the derived local region.
CHECKPOINT_EVERY_CASES = 10
TOP_CASES_FOR_FINE = 60
TOP_CASES_TO_VERIFY = 20
RANDOM_SEED = 20261012  # Different samples from the earlier runs.
FINE_PADDING_FRACTION = 0.12  # Full-range fraction added on each side.

# ---------------------------------------------------------------------------
# Objective and constraints
# ---------------------------------------------------------------------------
BURN_TIME_MIN_S = 6.5
BURN_TIME_MAX_S = 8.5
GRAIN_LENGTH_MIN_M = 0.80
GRAIN_LENGTH_MAX_M = 1.02

# ---------------------------------------------------------------------------
# Independent sweep variables
# ---------------------------------------------------------------------------
CHAMBER_PRESSURE_PSIG = (335.0, 350.0)
FUEL_MASS_KG = (6.0, 9.4)
OXIDIZER_MASS_FLOW_KG_S = (2.0, 2.3)
INITIAL_PORT_DIAMETER_M = (0.091, 0.108)  # Diameter, not radius.

# ---------------------------------------------------------------------------
# Sweep-only coupled/fixed values
# ---------------------------------------------------------------------------
GRAIN_MAX_OD_IN = 5.75
GRAIN_MAX_OD_M = GRAIN_MAX_OD_IN * 0.0254

# S = (Ptank(abs) - Pc(abs)) / Pc(abs). Its upper bound follows from the
# initial tank-pressure cap separately for each chamber-pressure candidate.
MIN_INJECTOR_STIFFNESS = 0.274
MAX_INITIAL_TANK_PRESSURE_PSIG = 450.0

# Keep this run's result signature separate from earlier runs.
SWEEP_MODEL_VERSION = "cstar070-variable-stiffness-burn65to85-flow23-initial-probe-v7"

# Temporary sizing fill. The existing runner computes actual LOX consumption
# from this run and verifies top designs with the resulting required fill.
# The unchanged model still enforces its fixed geometric tank capacity.
SIZING_INITIAL_OXIDIZER_MASS_KG = 30.0

FUEL_DENSITY_KG_M3 = 900.0

# Existing non-swept inputs are inherited from model_runner.BASE_INPUTS.
