# Hybrid Rocket Thrust Curve Generator

A Python/Streamlit application and automated parameter sweep for the CSI Rockets hybrid motor simulation model. It uses MATLAB Engine for Python and an **external** MATLAB CEA interface for thermochemical calculations.

> **Status:** Research/design tool. Results are model predictions, not hardware qualification or flight-safety validation. This repository is not self-contained: the MATLAB CEA files are not bundled here.

## Components

| Purpose | Files |
| --- | --- |
| Manual simulation and application logic | `streamlit_app.py`, `model_runner.py`, `main.py`, `engine.py` |
| Engine, propellant, mass, atmospheric data | `engine_parameter.py`, `propellant_properties.py`, `mass_component.py`, `atmospheric_pressure.py` |
| Cached thermochemistry and setup | `cea_lookup.py`, `cea_lookup_config.py`, `build_cea_lookup.py`, `setup_matlab_path.py` |
| Configuration and automated sweeps | `sweep_config.py`, `sweep_runner.py` |
| Export and supporting modules | `file_generator.py`, `unit_converter.py`, `cea_mockup.py`, `input_settings.py` |
| Environment diagnostics | `check_environment.py` |

`cea_mockup.py` is retained as a legacy import dependency; active calculations use MATLAB `CEA2` through the MATLAB engine.

## Requirements

- Windows and PowerShell
- Python 3.12 (the version previously tested for this project)
- A compatible MATLAB installation and MATLAB Engine for Python
- The project-specific `MatlabCEA` directory containing a working `CEA2` implementation, stored **beside** this repository, not inside it
- Python packages from `requirements.txt` (includes the `matlabengine` package; confirm its version matches the installed MATLAB release)

Expected layout:

```text
work-directory/
├── thrust-curve-generator/
└── MatlabCEA/
    └── CEA2.m
```

The MATLAB interface and related data have separate provenance/licensing requirements and are not distributed in this repository.

## Setup (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python .\setup_matlab_path.py
python .\check_environment.py
```

`setup_matlab_path.py` adds the sibling `MatlabCEA` directory to MATLAB's path persistently. Use it only if that directory is correctly installed.

## Run the Streamlit UI

```powershell
.\run_ui.ps1
```

Alternative:

```powershell
python -m streamlit run streamlit_app.py
```

## Run the parameter sweep

```powershell
python .\sweep_runner.py --mode all
```

```powershell
python .\sweep_runner.py --mode coarse --plan-only
```

The current search ranges, sample counts, constraints and random seed are defined in `sweep_config.py`. Review that file rather than relying on archived sweep-size descriptions.

## Input and output locations

- `csv files/`: atmospheric-pressure input data. **Important:** the current `atmospheric_pressure.py` reads the CSV with the latest filesystem modification time; this is not deterministic across Git clones. Select and explicitly configure a validated three-column input dataset before using the repository for reproducible studies.
- `rse files/`: generated OpenRocket motor files. The directory is tracked via `.gitkeep`; generated `*.rse` files are ignored by Git.
- `sweep_results/`: generated sweep CSV/JSON outputs, ignored by Git.
- `user_settings/`: local UI inputs and CEA cache, ignored by Git.

## Further documentation

- [Quick Model Manual](Hybrid_Thrust_Curve_Generator_Quick_Manual.md)

For the latest sweep parameters, constraints, and
sample counts, see `sweep_config.py`.

## Sharing and licensing

Check CSI Rockets' sharing policy and original author/dependency rights before switching the repository from **Private** to **Public**. Do not add an open-source `LICENSE` until you have permission to grant those rights.
