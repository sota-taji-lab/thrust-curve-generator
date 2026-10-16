"""Shared CEA lookup configuration for Streamlit and SweepRunner.

Change CEA_MODEL_TAG whenever the MATLAB CEA2 implementation, reactants,
or thermochemistry data change. A readable CEA2 source file is additionally
hashed automatically by cea_lookup.py when MATLAB can locate it.
"""

MODE = "lookup"  # "lookup" or "direct"; sweep uses this default.
CEA_MODEL_TAG = "CEA2-lox-paraffin-v1"
PRESSURE_STEP_PSIA = 5.0
OF_STEP = 0.1
MAX_RELATIVE_ERROR = 0.001  # 0.1% for each of Tc, gamma, M, and c-star.
RECHECK_EVERY = 25  # Subsequent interpolations per cell before direct validation.
