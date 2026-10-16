# SweepRunner User Guide

## Purpose

`SweepRunner` repeatedly runs the existing hybrid-rocket engine model to maximize **Total Impulse** while retaining only designs with **Burn Time between 4.0 s and 7.0 s**.

It does **not** automate the Streamlit browser. Both Streamlit and SweepRunner call the same underlying model through `model_runner.py`.

## Current sweep definition

### Independent variables

| Variable | Range |
|---|---:|
| Chamber Pressure | 270–300 psig |
| Initial Fuel Mass | 5.0–7.0 kg |
| Initial Oxidizer Mass Flow Rate | 1.5–2.5 kg/s |
| Initial Port Diameter | 0.0946–0.1200 m |

The port-diameter range is the approximate global envelope compatible with the selected fuel-mass range, a 5.75 in grain OD, and the 0.80–1.02 m grain-length constraint. Candidates outside the grain-length constraint are rejected before MATLAB simulation and do not count toward the 100/200 requested simulation cases.

### Fixed / coupled only inside SweepRunner

- Maximum Grain Outer Diameter = **5.75 in = 0.14605 m**
- Initial Oxidizer Tank Pressure = **Chamber Pressure + 118 psi**
- Grain Length must satisfy **0.80–1.02 m**
- Burn Time must satisfy **4.0–7.0 s**
- Objective = maximize **Total Impulse**

These SweepRunner-only rules do not remove the manual Tank Pressure or editable Maximum Grain OD controls from Streamlit.

## Oxidizer-mass sizing method

Initial oxidizer mass is not swept as an independent variable.

For each sweep case, the runner temporarily uses **26 kg LOX** so the model can normally reach grain burnout before oxidizer depletion. After the run:

`Required Initial Oxidizer Mass = 26 kg - Final Oxidizer Mass`

This is the integrated oxidizer consumption produced by the model for that grain-burnout trajectory.

After the Fine sweep, the top 10 designs are automatically re-run with this calculated required oxidizer mass. `fine_top10_verified.csv` reports whether oxidizer depletion and `port_diameter = grain_max_od` match within approximately one simulation time step.

## Search method

### Coarse

- 100 geometry-valid engine simulations
- Latin Hypercube Sampling across the full input range
- Pc = 270 psig and Pc = 300 psig are explicitly included as boundary anchor cases
- Results are ranked by Total Impulse after applying constraints

### Fine

- Reads the top 10 feasible Coarse results
- Builds a narrower region around them with a 10% full-range padding
- 200 geometry-valid engine simulations using Latin Hypercube Sampling
- Ranks feasible results by Total Impulse
- Re-runs the top 10 using calculated required LOX mass

## Running from Windows PowerShell

Open the project folder in VS Code and open a PowerShell terminal.

Activate the existing virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Option A: run Coarse and Fine separately

```powershell
python .\sweep_runner.py --mode coarse
```

After Coarse is complete:

```powershell
python .\sweep_runner.py --mode fine
```

### Option B: run both automatically

```powershell
python .\sweep_runner.py --mode all
```

### Option C: PowerShell helper files

```powershell
.\run_sweep_coarse.ps1
.\run_sweep_fine.ps1
```

or:

```powershell
.\run_sweep_all.ps1
```

## Plan-only check

This checks candidate generation without starting MATLAB or running the motor model:

```powershell
python .\sweep_runner.py --mode coarse --plan-only
```

## Output files

All output is written to `sweep_results/`.

### Coarse

- `coarse_all.csv` — all 100 simulation attempts
- `coarse_feasible.csv` — Burn Time / geometry / tank-capacity constraints passed, ranked by Total Impulse
- `coarse_top10.csv` — top 10 used to define Fine search area
- `coarse_bounds.json` — Coarse bounds used

### Fine

- `fine_all.csv` — all 200 simulation attempts
- `fine_feasible.csv` — feasible cases ranked by Total Impulse
- `fine_top10.csv` — top Fine cases
- `fine_derived_bounds.json` — bounds generated from Coarse top results
- `fine_top10_verified.csv` — top designs re-run with required LOX mass
- `best_design.csv` — highest-ranked verified design row

## Main result columns

The CSVs include:

- Chamber Pressure
- Coupled Tank Pressure
- Initial Fuel Mass
- Initial Oxidizer Mass Flow Rate
- Initial Port Diameter
- Fixed Maximum Grain OD
- Derived Grain Length
- Required Initial Oxidizer Mass
- Model tank capacity
- Burn Time
- Total Impulse
- Average / Peak Thrust
- Average ISP
- Average O/F
- Initial oxidizer mass flux
- Average throat mass flux
- Final fuel / oxidizer mass
- Final port diameter
- Termination reason
- Constraint pass/fail columns

## Changing ranges later

Edit only `sweep_config.py` for normal SweepRunner changes. The main model and Streamlit UI do not need to be edited.

Important parameters include:

- `COARSE_CASES`
- `FINE_CASES`
- `CHAMBER_PRESSURE_PSIG`
- `FUEL_MASS_KG`
- `OXIDIZER_MASS_FLOW_KG_S`
- `INITIAL_PORT_DIAMETER_M`
- `GRAIN_LENGTH_MIN_M`, `GRAIN_LENGTH_MAX_M`
- `BURN_TIME_MIN_S`, `BURN_TIME_MAX_S`
- `GRAIN_MAX_OD_IN`
- `TANK_PRESSURE_ABOVE_CHAMBER_PSI`

## Notes

- MATLAB is imported once per SweepRunner process and reused for all cases.
- The legacy engine model still performs its original 1 ms time marching and CEA calls; SweepRunner changes the controller, not the engine physics.
- An interrupted sweep keeps the latest `coarse_all.csv` or `fine_all.csv` checkpoint, although the current version starts a new run from case 1 when re-launched.
