# Author: Aadam
# Edited: Tingmeng & Naomi & Theo

import time
import sys
import matplotlib.pyplot as plt
import CoolProp.CoolProp as cp
import pandas as pd
import numpy as np
# from alive_progress import alive_bar

import file_generator as fg
import engine as eng
import engine_parameter as eng_param
import mass_component
import unit_converter as unit

# ============================================================================
# Simulation configuration
# ============================================================================

MIN_THRUST = 8000 # N *** what is the min. thrust needed for apogee 50,000ft

CHAMBER_PRESSURE = 300 # psig ** FOS Al—6061 T6: 3.404; T4: 1.702

COPV_LENGTH = 0.47 # m **
COPV_DRY_MASS = 3.9 # kg **

# Enter the fuel and oxidizer here.
FUEL_ID = "PARAFFIN"
OX_ID = "LOX"
PRESS_ID = "Nitrogen"
OX_PVAP_PSI = 0 # psi (vapor pressure = atmospheric / 0 for CoolProp usage in this model)

# NUM_ITR removed — not used

# ============================================================================
# Mass-component configuration
# ============================================================================

# MASS COMPONENTS
# How this works: enter a tabx

UNIT = unit.unit ()
thisEng = eng.engine (MIN_THRUST, CHAMBER_PRESSURE, FUEL_ID, OX_ID, PRESS_ID, UNIT.psig_To_Pa (OX_PVAP_PSI))

engine_array = []
engine_scores = []

# Create mass components for CG simulation. This can be summarized as follows:
"""
(mass, local_cg, length, reference)
    -> Mass = component mass
    -> Local_cg = z index of the component CG where the bottom of the component is z=0.
    -> Length = Simulated length of the component. Length > local_cg.
    -> Reference = where the location is indexed with respect to, for example "CC", "OX", or "ABS" (absolute)
        - An example is the p-valve. It is between the CC and Ox tank, so it has a reference of "CC".
        - Another example is the nozzle. It is below the CC, so it has a reference of "ABS".
"""

#sun 5 apr
upper_cc = mass_component.part (1.180667826, 1.480748896, 0.07112, "ABS") # Copy of Sheet3, fixed upper hardware

lower_cc = mass_component.part (2.662613559, 0.2850052543, 0.204597, "ABS") # Copy of Sheet3, fixed lower hardware
nozzle = mass_component.part (3.897, 0.1209618424, 0.19, "ABS") #nozzle

interstage_cc_ox = mass_component.part (4.389, 0.07192547133, 0.231124, "CC") # run valve + injector
interstage_ox_copv = mass_component.part (7.627, 0.2046026227, 0.310007, "OX") #gn2

# ============================================================================
# Engine initial conditions
# ============================================================================

# Engine Parameters:
ox_mass = 30-0.723-5.8799 # kg, flight fill ** (was 11.34) 3520K for an O/F ratio of 2.8 https://www.eucass.eu/doi/EUCASS2019-0488.pdf
fuel_mass = 10.8 # kg, flight cast #14.1*0.626469 #6kg = 8s #O-motor: 5.8kg, 0.135m port diameter
port_diameter = 0.101 # m #12s fuel port diameter = 0.078m, 10.016s = 0.101m
ox_mdot = 2.31 #kg/s
expansion_ratio = 4.5 # m^2/m^2 #4.9

#Total Impulse: 97743.5635 Ns

# ============================================================================
# Pressurization inputs
# ============================================================================

# Pressurization:
target_press_psig = 418 # psig (initial tank pressure, constant throughout simulation)
press_temp = 320

copv_pressure_psi = 4350 # psig ** max 300bar
copv_vol_L = 6.8 # L **
copv_len = 0.533 # m ** https://syacecare.com/product/1pcs-wholesale-acecare-dot-certified-6-8l-415ci-300bar-pcp-scuba-tank-with-integral-filling-station-valve/

target_press_Pa = UNIT.psig_To_Pa (target_press_psig)
copv_vol = copv_vol_L / 1000
init_press_mass = copv_vol * cp.PropsSI ('D','P|gas', UNIT.psig_To_Pa (copv_pressure_psi), 'T', press_temp, PRESS_ID)

# ============================================================================
# Simulation execution
# ============================================================================

this_itr = eng_param.engine_parameter (ox_mass, fuel_mass, port_diameter, ox_mdot, expansion_ratio, init_press_mass)
thisEngInstance = thisEng.run_simulation (this_itr, target_press_Pa, COPV_LENGTH, COPV_DRY_MASS, copv_vol, lower_cc, upper_cc, nozzle, interstage_cc_ox, interstage_ox_copv)
thisEngInstance.print_parameters ()
engine_array.append (thisEngInstance)
engine_scores.append (thisEngInstance.engine_score ())

# ============================================================================
# Result extraction and RSE export
# ============================================================================

diam = round (thisEngInstance.diam, 4)
length = round (thisEngInstance.length, 4)
initWt = round (thisEngInstance.initWt, 4)
propWt = round (thisEngInstance.propWt, 4)
avgThrust = round (thisEngInstance.avg_thrust, 4)
peakThrust = round (max (thisEngInstance.thrust_curve), 4)
throatDia = round (thisEngInstance.throatDia, 4)
exitDia = round (thisEngInstance.exitDia, 4)
Itot = round (thisEngInstance.total_impulse, 4)
burn_time = round (thisEngInstance.total_time, 4)
massFrac = round (thisEngInstance.massFrac, 4)
avgISP = round (thisEngInstance.avg_isp, 4)

rseFile = fg.rse_file (thisEngInstance.time, thisEngInstance.thrust_curve, thisEngInstance.m_curve, thisEngInstance.cg_curve, diam, length, initWt, propWt, 
                        0, 0, 0, avgThrust, peakThrust, throatDia, exitDia, 
                        Itot, burn_time, massFrac, avgISP, 0, 0, 0, 0, 0, 0, 
                        0, 0, 0, 0, 0, 0)

#bug = does not generate .rse file unless plots closed
