"""Add the sibling MatlabCEA folder to the persistent MATLAB search path.

This helper changes only the MATLAB search path. It does not modify any
simulator source file, equation, model constant, or calculation sequence.
"""

from pathlib import Path

import matlab.engine


PROJECT_DIR = Path(__file__).resolve().parent
MATLAB_CEA_DIR = PROJECT_DIR.parent / "MatlabCEA"


def main():
    """Add MatlabCEA recursively to MATLAB path and save the path."""
    if not MATLAB_CEA_DIR.is_dir():
        raise FileNotFoundError(
            "Expected MatlabCEA next to thrust-curve-generator, but it was not found at: "
            + str(MATLAB_CEA_DIR)
        )

    print("Starting MATLAB...")
    eng = matlab.engine.start_matlab()

    try:
        print(f"MATLAB version: {eng.version()}")
        eng.addpath(eng.genpath(str(MATLAB_CEA_DIR)), nargout=0)

        cea2_path = eng.which("CEA2")
        if not cea2_path:
            raise RuntimeError("CEA2 could not be resolved after adding MatlabCEA.")

        save_status = eng.savepath()
        if int(save_status) != 0:
            raise RuntimeError(
                "MATLAB found CEA2, but savepath did not complete successfully."
            )

        print(f"CEA2 location: {cea2_path}")
        print("[OK] MatlabCEA was added to the persistent MATLAB search path.")
    finally:
        eng.quit()


if __name__ == "__main__":
    main()
