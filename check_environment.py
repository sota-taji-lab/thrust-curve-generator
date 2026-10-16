"""Check the external software required by the current simulator.

This helper does not run the thrust simulation and does not modify the model.
It can temporarily add a sibling MatlabCEA folder to the MATLAB search path
for the duration of this check.
"""

from importlib import import_module
from pathlib import Path
import sys


PYTHON_PACKAGES = (
    "numpy",
    "pandas",
    "scipy",
    "matplotlib",
    "CoolProp",
)

PROJECT_DIR = Path(__file__).resolve().parent
MATLAB_CEA_DIR = PROJECT_DIR.parent / "MatlabCEA"


def check_python_packages():
    """Report whether the Python-side dependencies can be imported."""
    print("Python environment")
    print(f"  Python executable: {sys.executable}")
    print(f"  Python version: {sys.version.split()[0]}")

    print("\nPython package check")
    for package in PYTHON_PACKAGES:
        try:
            module = import_module(package)
            version = getattr(module, "__version__", "version not reported")
            print(f"  [OK] {package}: {version}")
        except Exception as exc:
            print(f"  [FAIL] {package}: {exc}")


def check_matlab_and_cea():
    """Start MATLAB and verify that MATLAB can resolve the CEA2 function."""
    print("\nMATLAB / CEA check")

    try:
        import matlab.engine
    except Exception as exc:
        print(f"  [FAIL] MATLAB Engine for Python import: {exc}")
        return

    try:
        eng = matlab.engine.start_matlab()
    except Exception as exc:
        print(f"  [FAIL] MATLAB startup: {exc}")
        return

    try:
        matlab_version = eng.version()
        print(f"  [OK] MATLAB started: {matlab_version}")

        if MATLAB_CEA_DIR.is_dir():
            matlab_cea_path = str(MATLAB_CEA_DIR)
            eng.addpath(eng.genpath(matlab_cea_path), nargout=0)
            print(f"  [OK] Temporary MATLAB CEA path added: {MATLAB_CEA_DIR}")
        else:
            print(f"  [INFO] Sibling MatlabCEA folder not found: {MATLAB_CEA_DIR}")

        cea2_path = eng.which("CEA2")
        if cea2_path:
            print(f"  [OK] CEA2 resolved by MATLAB: {cea2_path}")
        else:
            print("  [FAIL] MATLAB started, but CEA2 could not be resolved.")
    finally:
        eng.quit()


if __name__ == "__main__":
    check_python_packages()
    check_matlab_and_cea()
