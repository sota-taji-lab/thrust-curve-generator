# Hybrid Thrust Curve Generator — Quick Model Manual

**Purpose.** This is a short guide to the equations and data flow in the current Streamlit application and external Coarse/Fine SweepRunner. It describes the implemented model, not a validated hardware prediction. Based on the project files reviewed on 14 October 2026.

## 1. How the pieces connect

| Stage | Main file | What it does |
|---|---|---|
| Inputs | `streamlit_app.py`, `model_runner.py` | Accepts one design, calculates initial tank pressure from injector stiffness, and stores UI inputs for the next session. |
| Fuel and oxidizer properties | `propellant_properties.py` | Selects fixed regression coefficients and fuel density for the chosen fuel/oxidizer pair; obtains liquid oxidizer density from CoolProp. The UI currently fixes the fuel to paraffin and the oxidizer to LOX. |
| Burn simulation | `engine.py` | Initializes grain/nozzle/injector geometry; advances port diameter, propellant masses, chamber pressure, flow, and thrust every 0.001 s. |
| Thermochemistry | `cea_lookup.py`, `cea_lookup_config.py`, MATLAB `CEA2` | Supplies chamber temperature, specific-heat ratio, molecular mass, and characteristic velocity as functions of chamber pressure and O/F. Lookup mode caches grid values and checks interpolations against direct CEA. |
| Vehicle mass | `mass_component.py` | Builds dry masses from the component inputs and the calculated grain length; updates LOX, fuel, wet mass, and center of gravity (CG). |
| Results | `engine_parameter.py`, `streamlit_app.py` | Integrates thrust, displays values, and optionally exports an RSE thrust/mass/CG time history. |
| Optimization | `sweep_runner.py`, `sweep_config.py` | Runs the same `model_runner.run_case()` for many designs, filters by constraints, and ranks feasible designs by total impulse. |

## 2. Design and geometry

The UI defines initial chamber pressure \(P_{c,0}\), injector stiffness \(S\), initial LOX flow, fuel mass, initial port **diameter**, maximum grain outer diameter, and nozzle expansion ratio. Gauge pressure is converted to absolute pressure before using stiffness:

\[
S=\frac{P_{t,0}^{\mathrm{abs}}-P_{c,0}^{\mathrm{abs}}}{P_{c,0}^{\mathrm{abs}}},\qquad
P_{t,0}^{\mathrm{psig}}=(P_{c,0}^{\mathrm{psig}}+P_{\mathrm{atm}}^{\mathrm{psi}})(1+S)-P_{\mathrm{atm}}^{\mathrm{psi}}.
\]

With initial fuel mass \(m_{f,0}\), fuel density \(\rho_f\), grain outer diameter \(D_o\), and initial port diameter \(D_0\), the model sizes a uniform cylindrical annulus:

\[
L_g=\frac{4m_{f,0}}{\pi\rho_f(D_o^2-D_0^2)}.
\]

The aluminum casing and Chambersafe masses in the grain section follow this calculated length. The LOX tank length is fixed at 1.1684 m; changing its fill mass changes liquid height, not tank length. The nozzle geometry is sized on the first step and then held fixed.

## 3. One burn step

For port diameter \(D\) and LOX mass flow \(\dot m_o\), the current paraffin/LOX regression law is

\[
G_o=\frac{4\dot m_o}{\pi D^2},\qquad
\dot r=10^{-3}aG_o^n,\qquad
\dot m_f=\rho_f\dot r\,\pi DL_g,\qquad
O/F=\frac{\dot m_o}{\dot m_f}.
\]

The implemented constants are \(a=0.117\), \(n=0.62\), and \(\rho_f=900\,\mathrm{kg/m^3}\). Here \(G_o\) is **oxidizer mass flux**, \(\dot r\) is **fuel regression rate**, and \(10^{-3}\) converts the empirical regression result from mm/s to m/s. The geometry and remaining masses advance as

\[
D_{k+1}=D_k+2\dot r_k\Delta t,\quad
m_{f,k+1}=m_{f,k}-\dot m_{f,k}\Delta t,\quad
m_{o,k+1}=m_{o,k}-\dot m_{o,k}\Delta t,
\qquad \Delta t=0.001\,\mathrm{s}.
\]

At startup, the specified LOX flow and pressure difference determine a fixed effective injector area. Thereafter, with fixed tank pressure in this model,

\[
\dot m_o=C_{d,i}A_i\sqrt{2\rho_o(P_t-P_c)},
\qquad C_{d,i}=0.61.
\]

Thus chamber pressure can alter LOX flow during the burn; the initial flow setting is not an all-time flow limit. The model does not simulate regulator response or LOX tank blowdown.

Every 100 time steps (0.1 s), CEA is queried at the current chamber **absolute** pressure and O/F. Its \(c^*\) is multiplied by the current fixed efficiency of 0.70. Between queries, the last CEA properties are reused. With nozzle discharge coefficient \(C_{d,n}=0.99\), the first step sets

\[
A_t=\frac{(\dot m_o+\dot m_f)c^*}{C_{d,n}P_c},\qquad
A_e=A_t\varepsilon;
\]

subsequent steps use fixed \(A_t\) and \(A_e\), and estimate \(\dot m_n=C_{d,n}P_c A_t/c^*\). Chamber pressure is updated from the ideal-gas relation after adding \((\dot m_o+\dot m_f-\dot m_n)\Delta t\) to the gas mass inferred from the **current** \(P_c,T_c,M,V\). The code recalculates this starting gas mass at every step; it does not independently carry a conserved chamber-gas state or solve an energy balance.

The nozzle routine solves exit pressure from an isentropic area relation, then computes momentum thrust plus pressure thrust, \(F=F_{\mathrm{momentum}}+(P_e-P_a)A_e\). Ambient pressure \(P_a\) comes from the project's time-indexed pressure data. The run stops at grain burnout, LOX depletion, or the 30 s guard.

## 4. Mass, CG, and reported performance

The wet mass is dry hardware + remaining LOX + remaining fuel + pressurant. The CG is the mass-weighted average of component positions, measured from the nozzle exit. LOX CG follows the shrinking liquid column; remaining fuel stays centered along the grain. Pressurant mass is held at the COPV CG: transfer into the LOX tank is not modeled. LOX slosh is not modeled.

The reported total impulse and average specific impulse use

\[
I_t\approx\sum_k\frac{F_k+F_{k-1}}{2}(t_k-t_{k-1}),\qquad
I_{sp,\mathrm{avg}}=\frac{I_t}{g_0\,[\,(m_{f,0}+m_{o,0})-(m_{f,\mathrm{end}}+m_{o,\mathrm{end}})\,]}.
\]

The RSE file is created only when the user selects its export action; it uses the calculated thrust, vehicle mass, and CG histories.

## 5. Sweep and interpretation

The external SweepRunner samples chamber pressure, initial fuel mass, initial LOX flow, initial port diameter, and injector stiffness. Coarse searches broadly; Fine searches mostly around the best feasible Coarse cases, with an optional global fraction. A generous sizing LOX fill is intended to let the grain burn out; actual LOX consumption is then inferred, and top cases are rerun with that required fill. Passing cases meet the configured burn-time and grain-length windows, modeled tank capacity, grain burnout, and **initial** tank-pressure cap; feasible cases are ranked by total impulse.

**Model boundaries:** The supplied 2.3 kg/s exploratory sweep config limits *initial* LOX flow only. The sweep does not enforce peak LOX flow or peak chamber pressure throughout the burn. Fuel is treated as one homogeneous paraffin component; aluminum loading, separate condensed products, and their effects on gas/nozzle dynamics are not represented. Replacing only the regression coefficients would therefore not constitute an aluminum-loaded motor performance model.

**Code locations:** `model_runner.py` connects the UI and sweep to `engine.py`; `propellant_properties.py` holds \(a,n,\rho_f\); `mass_component.py` defines geometry and CG; `cea_lookup.py` handles direct/cached CEA; `sweep_config.py` holds external search ranges and constraints.
