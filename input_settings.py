"""Small, versioned on-disk store for Streamlit's editable numeric inputs."""

import json
import math
import os
import tempfile
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent / "user_settings" / "last_inputs.json"
MASS_REFERENCE = "combustion-devices-copy-of-sheet3-2026-10-09"
PREVIOUS_DEFAULTS = {
    "grain_max_od": 0.15875,
    "upper_cc_mass": 1.220054,
    "upper_cc_local_cg": 1.480101922,
    "lower_cc_mass": 2.711445995,
    "lower_cc_local_cg": 0.2856933172,
}


def load_inputs(defaults, path=SETTINGS_PATH):
    """Use only known, finite numeric fields; retain defaults for missing fields."""
    values = dict(defaults)
    if not Path(path).exists():
        return values
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("inputs"), dict):
        raise ValueError("Unsupported saved-input format")
    for key, default in defaults.items():
        saved = payload["inputs"].get(key)
        if type(default) in (float, int) and type(saved) in (float, int):
            if math.isfinite(saved):
                if (payload.get("mass_reference") != MASS_REFERENCE
                        and key in PREVIOUS_DEFAULTS
                        and math.isclose(saved, PREVIOUS_DEFAULTS[key], rel_tol=0, abs_tol=1e-12)):
                    # Replace only untouched defaults from the older workbook;
                    # preserve any genuinely edited/saved component values.
                    values[key] = default
                else:
                    values[key] = float(saved)
        elif key == "cea_mode" and saved in ("lookup", "direct"):
            values[key] = saved
    return values


def save_inputs(values, path=SETTINGS_PATH):
    """Atomically save the current form; keep the file intact on write failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {key: value for key, value in values.items()
             if (type(value) in (float, int) and math.isfinite(value))
             or (key == "cea_mode" and value in ("lookup", "direct"))}
    fd, temporary = tempfile.mkstemp(prefix=".last_inputs_", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump({"version": 1, "mass_reference": MASS_REFERENCE, "inputs": clean}, out, indent=2, ensure_ascii=False)
            out.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path
