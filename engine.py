# Author: Aadam Awad
import os
import io
import time
import sys
import socket
import math
import pandas as pd
import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import curve_fit
from scipy.optimize import fsolve
import matplotlib.pyplot as plt  
import matlab.engine
import CoolProp.CoolProp as cp

from CoolProp.CoolProp import AbstractState

import file_generator as fg
import engine_parameter as eng_param
import cea_mockup as Cea
import unit_converter as unit
import atmospheric_pressure as atmo
import mass_component as moc
import propellant_properties as prop
from cea_lookup import CeaLookup

start_time = time.time ()

print ("Starting Matlab ...", end = '\r', flush = True)
eng = matlab.engine.start_matlab()
sys.setrecursionlimit (65520)

# ============================================================================
# Model constants
# ============================================================================

# Todo:
#[FOR NOZZLE]
# - AVERAGE MASS FLUX OF CHAMBER
# - CONTRACTION RATIO
# - AMBIENT PRESSURE V APOGEE (OPENROCKET)
# - MIN AMBIENT PRESSURE @ 8,300 FT

# - Make ox mass flow a variable function of chamber pressure
# - Add blowdown model for after COPV is expended assuming closed E-Reg
# [DONE] Ideal solution and make a modified solution with a pressure knockdown of 80%
# [DONE] Shifting CG during burn
# [DONE] Add ESEOD + flow rates for pressurant
# [DONE] Make chamber pressure vary based on OF mass gain
# [DONE] Add ISP and average ISP code
# [TO DO] TRACKING PRESSURANT MOVING FROM COPV TO OX TANK 

PROP_OD_M = 0.1778      # m, 7 in vehicle/tank diameter used in RSE output
# Copy of Combustion Devices Mass Calcs / Copy of Sheet3 (matching the UI).
CC_AL_OD_M = 0.1651      # m, 6.5 in aluminum casing OD
CC_ID = 0.15875         # m, 6.25 in aluminum ID / Chambersafe OD
GRAIN_MAX_OD = 0.14605  # m, 5.75 in Chambersafe ID at the sheet reference
CC_AL_REFERENCE_MASS_KG = 5.437
CC_REFERENCE_GRAIN_LENGTH_M = 1.0434
CC_CS_REFERENCE_LENGTH_M = 1.0186
CC_AL_DENSITY_KG_M3 = 2700.0
CC_CS_DENSITY_KG_M3 = 1011.0
# The sheet's 5.437 kg Al casing is 6.43 minus two end pieces. It does not
# equal the annulus mass calculated from its displayed 6.5/6.25 in diameters.
# Preserve the sheet's nominal mass and use its displayed geometry for the
# change in mass as grain length changes. The unexplained reference residual
# is held fixed at the middle section CG pending a hardware reconciliation.
CC_AL_MASS_PER_LENGTH = CC_AL_DENSITY_KG_M3 * math.pi * 0.25 * (CC_AL_OD_M**2 - CC_ID**2)
CC_AL_REFERENCE_OFFSET_KG = CC_AL_REFERENCE_MASS_KG - CC_AL_MASS_PER_LENGTH * CC_REFERENCE_GRAIN_LENGTH_M
CC_CS_LENGTH_OFFSET_M = CC_REFERENCE_GRAIN_LENGTH_M - CC_CS_REFERENCE_LENGTH_M


def cc_cs_mass_per_length(grain_max_od):
    if not 0 < grain_max_od < CC_ID:
        raise ValueError("Maximum grain OD must be between zero and Chambersafe OD.")
    return CC_CS_DENSITY_KG_M3 * math.pi * 0.25 * (CC_ID**2 - grain_max_od**2)

TANK_ID = 0.17145 # m , 6.75 in ** 7 tank OD, 0.125 wall thickness
TANK_WALL_THICKNESS = 0.003175 # m , 0.125 in
CSTAR_EFFICIENCY = 0.70 # Dimensionless, based on chamber geometry and mixing


# Combustion Chamber Geometry <4/5 update>
PRECOMBUSTOR_LENGTH = 0.07112  # m ** 2.8in ~0.5*ID
POSTCOMBUSTOR_LENGTH = 0.204597 # m *** 8.055in 

# Tank Features
OX_MASS_PER_LENGTH = math.pi * 0.25 * ((TANK_ID + TANK_WALL_THICKNESS*2)**2 - TANK_ID**2) * 2700 + 0.88513 # ** value restored from pre-UI configuration
CC_MASS_PER_LENGTH = CC_AL_MASS_PER_LENGTH + cc_cs_mass_per_length(GRAIN_MAX_OD)
ULLAGE_RATIO = 0.10 # budget for boiloff, controlled by QD, can be adjusted/measured, how empty tank is

# For the SciPy fsolve function, it requires a guess before solving the iterative function.
MACH_EXIT_GUESS = 4

# Ideal Gas
R = 8.31446261815324 # J * mol^-1 * K^-1 
Rp = 8314.46261815324 # J * kg^-1 * mol^-1 * K^-1
MW_N2 = 0.028013      # kg / mol
MW_O2 = 0.031999      # kg / mol

UNIT = unit.unit ()

NOZZLE_DISCHARGE_COEFFICIENT = 0.99 # based on machining a highly optimized contour
INJECTOR_DISCHARGE_COEFFICIENT = 0.61 # based on injector geometry *** NEED TO UPDATE BASED ON INJECTOR DESIGN ***

# Simulation time step. Decrease for a longer run time.
TIME_STEP = 0.001

# Loops per NASA CEA call. The smaller the better. Must be an integer
LOOPS_PER_CEA_ITERATION = 100

# ============================================================================
# Hybrid motor simulation
# ============================================================================

class engine:

    # ------------------------------------------------------------------------
    # Simulation initialization
    # ------------------------------------------------------------------------
    def run_simulation (self, eng_param_instance, init_press, copv_length, copv_dry_mass, copv_vol, lower_cc, upper_cc, nozzle, interstage_cc_ox, interstage_ox_copv):
        
        self.Pc = self.Pc_fixed
        self.alt = 0
        self.t = 0
        self.thrust_curve = []
        self.coef_curve = []
        self.cg_curve = []
        self.m_curve = []
        self.of_curve = []
        self.eseod_curve = []
        self.throat_mass_flux = []
        self.p_curve = []
        self.t_curve = []
        self.time = []

        self.iteration_tracker = 0

        self.eng_param_instance = eng_param_instance
        self.init_ox_mass = eng_param_instance.get_ox_mass()
        self.init_fuel_mass = eng_param_instance.get_fuel_mass()
        self.init_press_mass = eng_param_instance.get_press_mass()
        self.init_port_diameter = eng_param_instance.get_port_diameter()
        self.init_ox_mdot = eng_param_instance.get_ox_mdot()
        self.expansion_ratio = eng_param_instance.get_expansion_ratio()
        
        self.press = init_press

        self.copv_length = copv_length
        self.copv_dry_mass = copv_dry_mass
        self.copv_vol = copv_vol

        self.ox_mass = self.init_ox_mass
        self.fuel_mass = self.init_fuel_mass
        self.press_mass = self.init_press_mass
        self.port_diameter = self.init_port_diameter
        self.ox_mdot = self.init_ox_mdot

        self.grain_length = self.find_grain_length()

        self.thisMoc = moc.massComp (upper_cc, lower_cc, nozzle, interstage_cc_ox, interstage_ox_copv, OX_MASS_PER_LENGTH, 
                      self.ox_density, self.copv_length, self.copv_dry_mass, self.cc_mass_per_length, self.fuel_density, PRECOMBUSTOR_LENGTH, POSTCOMBUSTOR_LENGTH, 
                      self.port_diameter, self.grain_max_od, TANK_ID, self.ox_mass, self.fuel_mass, self.press_mass, ULLAGE_RATIO,
                      CC_AL_MASS_PER_LENGTH, self.cc_cs_mass_per_length, CC_CS_LENGTH_OFFSET_M,
                      CC_AL_REFERENCE_OFFSET_KG)
        
        # Storing the initial dry mass and length
        self.dryMass, self.initLen_m = self.thisMoc.get_initWt_initLen()

        # Converting from m to mm
        self.initLen = self.initLen_m * 1000

        # Finding initial oxidizer vapor
        init_column_height = self.thisMoc.ox_column_height (self.ox_mass)
        if init_column_height > self.thisMoc.ox_length:
            raise Exception (
                "Initial oxidizer mass exceeds the capacity of the fixed "
                + str(round(self.thisMoc.ox_length, 4))
                + " m oxidizer tank."
            )
        init_vapor_vol = self.thisMoc.ox_tank_vol - init_column_height * (0.25 * math.pi * TANK_ID**2)
        # store vapor temperature; mass/moles not currently used
        self.nitrox_t = cp.PropsSI ('T','P', self.ox_pvap, 'Q', 1,'Oxygen')

        # Verifying Non-Malicious Inputs
        if (self.port_diameter > (self.grain_max_od + 0.001)):
            raise Exception ("Port diameter exceeds max grain diameter. Please enter a value of " + str (round (self.grain_max_od, 4)) + " m or lower.")

        return self.generate_thrust_curve (eng_param_instance)
    
    # ------------------------------------------------------------------------
    # Fuel-grain geometry
    # ------------------------------------------------------------------------
    def find_grain_length (self):

        return self.fuel_mass / (math.pi * self.fuel_density * (((self.grain_max_od / 2)**2) - ((self.port_diameter / 2)**2)))

    # ------------------------------------------------------------------------
    # Engine object initialization
    # ------------------------------------------------------------------------
    def __init__ (self, init_thrust, chamber_pressure, fuel_ID, ox_ID, press_ID, ox_pvap, grain_max_od=GRAIN_MAX_OD):
        
        self.cea = Cea.lox_paraffin ()
        self.cea_evaluator = CeaLookup(eng, fuel_ID, ox_ID)
        self.atmo = atmo.atmo ()

        self.min_thrust = init_thrust
        self.chamber_pressure_PSI = chamber_pressure
        self.Pc_fixed = UNIT.psig_To_Pa (chamber_pressure)

        # Placeholder
        self.At = 1
        self.Ae = 1

        self.throat_given = True

        thisProp = prop.prop (fuel_ID, ox_ID, ox_pvap)
        thisPress = prop.press (press_ID)

        self.press_ID = press_ID
        self.ox_ID = ox_ID

        # Per-run grain OD. This replaces use of the module-level constant inside
        # the simulation while keeping GRAIN_MAX_OD as the default/reference value.
        self.grain_max_od = grain_max_od
        self.cc_cs_mass_per_length = cc_cs_mass_per_length(self.grain_max_od)
        self.cc_mass_per_length = CC_AL_MASS_PER_LENGTH + self.cc_cs_mass_per_length

        self.a = thisProp.a
        self.n = thisProp.n

        self.fuel_density = thisProp.fuel_density
        self.ox_density = thisProp.ox_density
        self.ox_pvap = ox_pvap

        # press_molec_mass removed — not used in current model

    # Find the fuel grain geometry:
        # - The oxidizer tank is pressurized to an initial pressure
        # - The combustion chamber is pressurized to a set value, self.chamber_pressure
    # Instantaneous regression rate, based on (1.1), and dervied fuel_mdot.
    # ------------------------------------------------------------------------
    # Fuel regression and mass flow
    # ------------------------------------------------------------------------
    def current_fuel_mdot (self):
        # RPE Eqn 16-10
        # 0.001 is a correction factor such that r_dot is in m/s, keeping everything in SI.
        fuel_rdot = 0.001 * self.a * (self.ox_mdot/(math.pi*((self.port_diameter/2)**2)))**self.n
        # RPE Eqn 16-11
        fuel_mdot = math.pi * self.fuel_density * fuel_rdot * self.grain_length * self.port_diameter
        return fuel_mdot, fuel_rdot
    
    # Instantaneous mass flow rate.
    def current_mass_flow (self):
        fuel_mdot, fuel_rdot = self.current_fuel_mdot ()
        # print (fuel_rdot)
        # HRAP Eqn 13
        of_ratio = self.ox_mdot / fuel_mdot
        #print (fuel_mdot, self.ox_mdot)
        return fuel_mdot, fuel_mdot + self.ox_mdot, of_ratio, fuel_rdot


    # ------------------------------------------------------------------------
    # Time-marching thrust-curve calculation
    # ------------------------------------------------------------------------
    def generate_thrust_curve (self, init_params):
        
        print ("Progress [" + str (round (100*(1 - (self.grain_max_od - self.init_port_diameter - (self.port_diameter - self.init_port_diameter))/(self.grain_max_od - self.init_port_diameter)), 1)) + "%]      ", 
               end="\r", flush = True)

        # Parameterizing the ambient air pressure in Pa
        self.Pa = self.atmo.air_pressure (self.t)

        # Throat Area is parameterized at engine startup. Established a filter that if Pc > 500 psia the simulation should end.
        fuel_mdot, generated_mdot, of_ratio, fuel_rdot = self.current_mass_flow ()

        if (self.iteration_tracker % LOOPS_PER_CEA_ITERATION == 0):
            # Performs a binary search to find the parameters within +- 5 m/s of the target knocked down characteristic velocity
            self.Tc, self.gamma, self.molecular_mass, self.characteristic_velocity = self.cea_evaluator.get (UNIT.Pa_to_psia (self.Pc), of_ratio)
            self.characteristic_velocity = self.characteristic_velocity * CSTAR_EFFICIENCY

            # Converting from g/mol to kg/mol
            self.molecular_mass = self.molecular_mass / 1000

        # HRAP Eqn 16
        # The throat is only updated for the first iteration, then inputted as a fixed parameter for future iterations.
        
        if self.throat_given is True:

            self.At = generated_mdot * self.characteristic_velocity / (NOZZLE_DISCHARGE_COEFFICIENT * self.Pc)
            self.Ae = self.At * self.expansion_ratio

            throatDia_m = math.sqrt (4 * self.At/math.pi)
            self.throatDia = 1000 * throatDia_m
            exitDia = math.sqrt (4 * self.Ae/math.pi)
            self.exitDia = 1000 * exitDia

            # Waxman Eqn 2.17
            self.injector_area = self.ox_mdot / (INJECTOR_DISCHARGE_COEFFICIENT * math.sqrt (2 * self.ox_density * (self.press - self.Pc)))
        
        # Oxidizer mass flow rate is found from the injector area.

        # print ("Chamber Pressure: ", self.Pc)
        # print ("Ox Density: ", self.ox_density)
        # print ("Tank Pressure: ", self.press)

        self.ox_mdot = self.injector_area * (INJECTOR_DISCHARGE_COEFFICIENT * math.sqrt (2 * self.ox_density * (self.press - self.Pc)))

        # HRAP Eqn 18
        # Evolving chamber pressure model, ideal gas assumption

        nozzle_mdot = NOZZLE_DISCHARGE_COEFFICIENT * self.Pc * self.At / self.characteristic_velocity

        #print("Nozzle mdot:", nozzle_mdot)

        throat_mass_flux = nozzle_mdot / self.At
        
        temp_v = self.thisMoc.get_cc_volume (self.port_diameter)
        gain_mdot = generated_mdot - nozzle_mdot
        gas_mass = self.molecular_mass * self.Pc * temp_v / (R * self.Tc)
        gas_mass = gas_mass + (gain_mdot * TIME_STEP)
        self.Pc = (gas_mass/self.molecular_mass) * R * self.Tc / temp_v
        # print (UNIT.Pa_to_psig (self.Pc))
        # print (UNIT.Pa_to_psig (self.press))
 
        # - RPE Eqn 3-25
        def exit_pressure (Pe):
            return (((self.gamma + 1)/2)**(1/(self.gamma-1)))*((Pe/self.Pc)**(1/self.gamma))*(((self.gamma+1)/(self.gamma-1))*(1 - (Pe/self.Pc)**(((self.gamma-1)/self.gamma))))**(1/2) - self.At/self.Ae
        self.Pe = fsolve (exit_pressure, self.Pa) [0]
        # print (self.Pe)

        # - RPE Eqn 3-22
        self.Tt = 2 * self.Tc/(self.gamma + 1)

        # - HRAP Eqn 21, doesn't influence thrust calculations but it can provide useful information for test stand sizing.
        self.Te = self.Tc * (self.Pe/self.Pc)**((self.gamma-1)/self.gamma)

        # - RPE Eqn 3-29
        f = self.At*self.Pc*math.sqrt((2*self.gamma**2)/(self.gamma-1) * (2/(self.gamma+1))**((self.gamma+1)/(self.gamma-1)) * (1 - ((self.Pe/self.Pc)**((self.gamma-1)/self.gamma)))) + (self.Pe-self.Pa)*self.Ae
        Cf = f/(self.Pc * self.At)

        self.ox_vdot = self.ox_mdot / self.ox_density # Oxidizer volumetric flow rate

        self.cg, self.mass = self.thisMoc.current_cg_wet_mass (self.ox_mass, self.fuel_mass, self.press_mass)

        propWt_kg = self.fuel_mass + self.ox_mass
        self.propWt = propWt_kg * 1000

        # Storing the initial wet mass and propellant weight
        if self.throat_given is True:
            
            self.initPropWt = self.propWt
            self.initWt = self.mass * 1000

        self.m_curve.append (self.mass*1000)
        self.of_curve.append (of_ratio)
        self.cg_curve.append (self.cg*1000)
        self.thrust_curve.append (f)
        # f = 4.4482216153 * (-8.79384353e-36*((self.t * 10**6)**6)+1.43134712e-28*((self.t * 10**6)**5)+(-9.28919796e-22)*((self.t * 10**6)**4)+(3.08819372e-15)*((self.t * 10**6)**3)+(-5.55791748e-09)*((self.t * 10**6)**2)+(4.71395307e-03)*self.t*10**6+(-9.31685956e+01))
        # print (f)
        # self.thrust_curve.append (abs (f))
        self.coef_curve.append (Cf)
        self.throat_mass_flux.append (throat_mass_flux)
        self.p_curve.append (self.press)
        self.t_curve.append (self.nitrox_t)
        self.time.append (self.t)

        # Recursive end cases. If the vehicle runs out of fuel or oxidizer it will end the simulation. I also imposed
        # an arbitrary 30 second limit for reasonable motor designs. It should not reach this limit and is intended
        # as a safeguard for excessive recursion depth.

        # Iterate
        self.t = self.t + TIME_STEP
        self.port_diameter = self.port_diameter + 2*fuel_rdot*TIME_STEP
        self.fuel_mass = self.fuel_mass - fuel_mdot*TIME_STEP
        self.ox_mass = self.ox_mass - self.ox_mdot*TIME_STEP

        #print("Fuel mdot:", fuel_mdot)
        
        self.iteration_tracker += 1
        self.throat_given = False

        if self.port_diameter >= self.grain_max_od:

            self.port_diameter = self.grain_max_od

        if self.ox_mass <= 0:

            self.ox_mass = 0

        grain_burnout = self.port_diameter >= self.grain_max_od
        oxidizer_depleted = self.ox_mass <= 0
        time_limit = self.t > 30

        if grain_burnout or oxidizer_depleted or time_limit:
        # if (self.port_diameter >= GRAIN_MAX_OD or self.ox_mass <= 0) and f < 0:

            if grain_burnout and oxidizer_depleted:
                termination_reason = "GRAIN_BURNOUT+OXIDIZER_DEPLETED"
            elif grain_burnout:
                termination_reason = "GRAIN_BURNOUT"
            elif oxidizer_depleted:
                termination_reason = "OXIDIZER_DEPLETED"
            else:
                termination_reason = "TIME_LIMIT"

            final_params = eng_param.engine_parameter (self.ox_mass,
                                                        self.fuel_mass,
                                                        self.port_diameter,
                                                        self.ox_mdot,
                                                        self.expansion_ratio,
                                                        self.press)

            self.thisMoc.print_mass_comp ()
            this_result = eng_param.engine_result (init_params, final_params, self.grain_length, self.thrust_curve, self.coef_curve, self.cg_curve, self.m_curve, self.of_curve, self.thisMoc, self.Tc, self.Tt, 
                                                   self.Te, self.p_curve, self.t_curve, self.time, 1000 * PROP_OD_M, self.initLen, self.initWt, self.initPropWt, 
                                                   self.throatDia, self.exitDia, 100 * self.propWt/self.initWt, self.throat_mass_flux)
            this_result.grain_max_od = self.grain_max_od
            this_result.termination_reason = termination_reason
            this_result.oxidizer_consumed_kg = self.init_ox_mass - self.ox_mass
            this_result.cea_stats = dict(self.cea_evaluator.stats)
            this_result.cea_mode = self.cea_evaluator.mode
    
            return this_result
        else:
            return self.generate_thrust_curve (init_params)
