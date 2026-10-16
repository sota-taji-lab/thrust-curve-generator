# Author: Aadam Awad

import matplotlib.pyplot as plt
import CoolProp.CoolProp as cp
import math
import unit_converter as unit
UNIT = unit.unit ()

class engine_parameter:

    def __init__ (self, ox_mass, fuel_mass, port_diameter, ox_mdot, expansion_ratio, press_mass):

        self.ox_mass = ox_mass
        self.fuel_mass = fuel_mass
        self.port_diameter = port_diameter
        self.ox_mdot = ox_mdot
        self.expansion_ratio = expansion_ratio
        self.press_mass = press_mass

    def get_ox_mass (self):
        return self.ox_mass
    
    def get_fuel_mass (self):
        return self.fuel_mass
    
    def get_port_diameter (self):
        return self.port_diameter
    
    def get_ox_mdot (self):
        return self.ox_mdot
    
    def get_expansion_ratio (self):
        return self.expansion_ratio
    
    def get_press_mass (self):
        return self.press_mass
    
class engine_result:

    def __init__ (self, input_param, final_param, grain_length, thrust_curve, coef_curve, cg_curve, m_curve, of_curve, thisMoc, Tc, Tt, Te, p_curve, t_curve, time, 
                  diam, length, initWt, propWt, throatDia, exitDia, massFrac, throat_mass_flux):

        self.input_param = input_param

        self.init_ox_mass = input_param.get_ox_mass()
        self.init_fuel_mass = input_param.get_fuel_mass()
        self.init_press_mass = input_param.get_press_mass()
        self.grain_length = grain_length
        self.init_port_diameter = input_param.get_port_diameter()
        self.init_ox_mdot = input_param.get_ox_mdot()
        self.expansion_ratio = input_param.get_expansion_ratio()

        self.tank_length = thisMoc.ox_length

        self.final_ox_mass = final_param.get_ox_mass()
        self.final_fuel_mass = final_param.get_fuel_mass()
        self.final_port_diameter = final_param.get_port_diameter()
        self.final_ox_mdot = final_param.get_ox_mdot()
        
        self.thrust_curve = thrust_curve
        self.coef_curve = coef_curve
        self.cg_curve = cg_curve
        self.m_curve = m_curve
        self.of_curve = of_curve
        self.p_curve = p_curve
        self.t_curve = t_curve
        self.throat_mass_flux = throat_mass_flux
        self.total_impulse = 0
        self.time = time
        self.total_time = time [len(time) - 1]

        self.Tc = Tc
        self.Tt = Tt
        self.Te = Te

        self.diam = diam
        self.length = length
        self.initWt = initWt
        self.propWt = propWt
        self.throatDia = throatDia
        self.exitDia = exitDia
        self.massFrac = massFrac

        for thrust_index in range (1, len (thrust_curve)):

            self.total_impulse += (time [thrust_index] - time [thrust_index - 1]) * (thrust_curve [thrust_index] + thrust_curve [thrust_index - 1])/2

        self.avg_thrust = sum (thrust_curve) / len (thrust_curve)
        self.avg_coef = sum (coef_curve) / len (coef_curve)
        self.avg_isp = self.total_impulse / (9.80665 * ((self.init_fuel_mass + self.init_ox_mass) - (self.final_fuel_mass + self.final_ox_mass)))
        self.avg_of = sum(self.of_curve) / len(self.of_curve) if len(self.of_curve) > 0 else None
    
    def engine_score (self):
        return self.avg_isp - 100 * (self.final_fuel_mass + self.final_ox_mass)
    
    def print_parameters (self):
        print (" *** INITIAL CONDITIONS *** ")
        print ("Initial Oxidizer Mass: " + str (round (self.init_ox_mass, 4)) + " kg")
        print ("Initial Fuel Mass: " + str (round (self.init_fuel_mass, 4)) + " kg")
        print ("Initial Pressurant Mass: " + str (round (self.init_press_mass, 4)) + " kg")
        print ("     ---------------- ")
        print (" *** FINAL CONDITIONS ***")
        print ("Remaining Oxidizer: " + str (round (self.final_ox_mass, 4)) + " kg")
        print ("Remaining Fuel: " + str (round (self.final_fuel_mass, 4)) + " kg")
        print ("Final Port Diameter: " + str (round (self.final_port_diameter, 4)) + " m")
        print ("     ------------------ ")
        print (" *** OX CONDITIONS *** ")
        print ("Ox Tank Length: " + str (round (self.tank_length, 4)) + " m")
        print ("Ox Mass Flow Rate: " + str (round (self.init_ox_mdot, 4)) + " kg/s")
        print ("     ------------------ ")
        print (" *** CHAMBER CONDITIONS *** ")
        print ("Grain Length: " + str (round (self.grain_length, 4)) + " m")
        print ("Initial Port Diameter: " + str (round (self.init_port_diameter, 4)) + " m")
        print ("Max Port Mass Flux: " + str (round (self.init_ox_mdot/(0.25*math.pi*self.init_port_diameter**2), 4)) + " kg/m^2")
        print ("Chamber Temperature: " + str (round(self.Tc, 4)) + " K")
        print ("Throat Temperature: " + str (round(self.Tt, 4)) + " K")
        print ("Exit Temperature: " + str (round (self.Te, 4)) + " K")
        print ("     ----------- ")
        print (" *** NOZZLE CONDITIONS *** ")
        print ("Throat Diameter: " + str (round (self.throatDia, 4)) + " mm")
        print ("Exit Diameter: " + str (round (self.exitDia, 4)) + " mm")
        print ("Average Throat Mass Flux: " + str (round (sum(self.throat_mass_flux)/len(self.throat_mass_flux), 4)) + " kg/m^2")
        print ("Expansion Ratio: " + str (round (self.expansion_ratio, 4)))
        print ("     ----------- ")
        print (" *** PERFORMANCE ***")
        print ("Average Thrust: " + str (round (self.avg_thrust, 4)) + " N")
        print ("Max Thrust (N): " + str (round (max (self.thrust_curve), 4)) + " N")
        print ("Max Thrust (lbf): " + str (round (UNIT.N_to_lbf (max (self.thrust_curve)), 4)) + " lbf")
        print ("Burn Time: " + str (round (self.total_time, 4)) + " s")
        print ("Average Thrust Coefficient: " + str (round (self.avg_coef, 4)))
        print ("Total Impulse: " + str (round (self.total_impulse, 4)) + " Ns")
        print ("Average ISP: " + str (round (self.avg_isp, 4)) + " s")
        if hasattr(self, "termination_reason"):
            print ("Termination Reason: " + str(self.termination_reason))
        if hasattr(self, "oxidizer_consumed_kg"):
            print ("Oxidizer Consumed: " + str(round(self.oxidizer_consumed_kg, 4)) + " kg")
        self.disp_graphs ()


    def disp_graphs (self):

        plt.figure(figsize=(12, 6))
        plt.plot(self.time, self.thrust_curve, 'b-', linewidth=2)

        plt.xlabel('Time (seconds)')
        plt.ylabel('Thrust (N)')
        plt.title('P-' + str ( int (self.avg_thrust)) + ' Thrust Curve')

        plt.grid(True, linestyle='--', alpha=0.7)

        plt.fill_between (self.time, self.thrust_curve, alpha=0.2)  # Add area under the curve
        plt.xlim (min(self.time), max(self.time))  # Set x-axis limits
        plt.ylim (0, max(self.thrust_curve) * 1.25)  # Set y-axis limits with 10% margin

    # (tank pressure and temperature plots removed)
    # ---
    # plt.figure(figsize=(12, 6))
    # plt.plot(self.time, self.p_curve, 'b-', linewidth=2)

    # plt.xlabel('Time (seconds)')
    # plt.ylabel('Pressure (Pa)')
    # plt.title('P-' + str ( int (self.avg_thrust)) + ' Tank Pressure Curve')

    # plt.grid(True, linestyle='--', alpha=0.7)

    # plt.xlim (min(self.time), max(self.time))  # Set x-axis limits
    # plt.ylim (0, max(self.p_curve) * 1.25)  # Set y-axis limits with 10% margin

    # ---

    # plt.figure(figsize=(12, 6))
    # plt.plot(self.time, self.t_curve, 'b-', linewidth=2)

    # plt.xlabel('Time (seconds)')
    # plt.ylabel('Temperature (K)')
    # plt.title('P-' + str ( int (self.avg_thrust)) + ' Tank Temperature Curve')

    # plt.grid(True, linestyle='--', alpha=0.7)

    # plt.xlim (min(self.time), max(self.time))  # Set x-axis limits
    # plt.ylim (0, max(self.t_curve) * 1.25)  # Set y-axis limits with 10% margin

        # --- OF ratio vs Time ---
        if hasattr(self, 'of_curve') and len(self.of_curve) > 0:
            plt.figure(figsize=(12, 6))
            plt.plot(self.time, self.of_curve, color='purple', linewidth=2)
            plt.xlabel('Time (seconds)')
            plt.ylabel('O/F Ratio (kg/kg)')
            title_of = 'P-' + str(int(self.avg_thrust)) + ' O/F Ratio vs Time'
            if self.avg_of is not None:
                title_of += ' (avg {:.2f})'.format(self.avg_of)
            plt.title(title_of)
            plt.grid(True, linestyle='--', alpha=0.7)
            plt.xlim(min(self.time), max(self.time))
            # Set sensible y-limits around OF curve
            of_min = min(self.of_curve)
            of_max = max(self.of_curve)
            if of_min == of_max:
                plt.ylim(of_min * 0.9, of_max * 1.1 if of_max != 0 else 1)
            else:
                plt.ylim(of_min * 0.9, of_max * 1.1)

        plt.show()
