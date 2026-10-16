import math

# HOW THIS WORKS:
"""
Given a structural reference point, z0, all upstream components are defined in space with respect to that point. A simple version of this model has
3 sets of mass components:

    - Bottom of CC; the nozzle and any associated hardware with a fixed CG.
        - Future iterations can use a Method of Characteristics solver to determine the nozzle dimensions based on the throat and exit area. For now this
        will be approximate using the 2023-24 monolithic graphite nozzle and 6061-T6 jacket.
    - Interstage; the injector manifold, run valve, bottom ox tank bulkhead.
    - Top of Ox Tank: Top ox tank bulkhead, ereg valve, and pressurant COPV.

There are also mass components that evolve with parameters. This is too significant to neglect, so the model also solves for these parameters.

    - Ox Tank Length; fixed at the selected flight-tank hardware length (1.1684 m).
    - CC Length; varies linearly with the required fuel mass given a max OD and port diameter from the iterative solver.

The purpose of the first 3 mass component categories is that, given a z0 of the nozzle exit, the location of the interstage is a function of the combustion
chamber length. The oxidizer tank length is fixed for the selected hardware configuration.

Finally, the last step is modeling the shifting CG throughout the burn. This has three components:

    - Pressurant CG; currently held at the COPV center for the entire burn. Transfer into the ox tank is not yet modeled.
    - Oxidizer CG; Oxidizer will flow and be ejected from the vehicle. The CG of the ox tank will shift backwards throughout the burn.
    - Fuel CG; Fuel will also be combusted and ejected from the vehicle. The CG of the combustion chamber will shift throughout the burn.

The first set of 5 components will be fixed for a given engine configuration. The consumables CG will shift throughout a given burn and needs to be updated iteratively.

"""


# Fixed oxidizer-tank geometry from the latest pre-UI configuration.
# The tank length is intentionally NOT resized when initial oxidizer mass changes.
FIXED_OX_TANK_LENGTH = 1.1684  # m

# The upper chamber's existing ABS CG input comes from the mass-calculation
# sheet at these nominal axial lengths. Convert that reference coordinate to
# an offset from the grain's upper end before placing it in a new design.
UPPER_CC_CG_REFERENCE_GRAIN_LENGTH = 1.0434  # m
UPPER_CC_CG_REFERENCE_LOWER_LENGTH = 0.204597  # m
UPPER_CC_CG_REFERENCE_NOZZLE_LENGTH = 0.19  # m

class massComp:

    def __init__ (self, upper_cc, lower_cc, nozzle, interstage_cc_ox, interstage_ox_copv,
                  ox_mass_per_length, ox_density,
                  copv_length, copv_mass,
                  cc_mass_per_length, fuel_density, precombustor_length, postcombustor_length,
                  port_diameter, cc_max_od,
                  ox_max_od, init_ox_mass, init_fuel_mass, init_press_mass, ullage_ratio,
                  cc_al_mass_per_length, cc_cs_mass_per_length, cc_cs_length_offset,
                  cc_al_reference_offset):

        self.upper_cc_comp = upper_cc
        self.lower_cc_comp = lower_cc
        self.nozzle_comp = nozzle
        self.interstage_cc_ox_comp = interstage_cc_ox
        self.interstage_ox_copv_comp = interstage_ox_copv
        self.cc_mass_per_length = cc_mass_per_length
        self.cc_al_mass_per_length = cc_al_mass_per_length
        self.cc_cs_mass_per_length = cc_cs_mass_per_length
        self.cc_cs_length_offset = cc_cs_length_offset
        self.cc_al_reference_offset = cc_al_reference_offset

        self.precombustor_length = precombustor_length
        self.postcombustor_length = postcombustor_length
        self.cc_max_od = cc_max_od

        self.ox_length = FIXED_OX_TANK_LENGTH
        # Previous UI-era behavior resized the tank from oxidizer mass and ullage.
        # That behavior is intentionally disabled for the fixed flight-tank geometry.
        self.ox_tank_vol = self.ox_length * (math.pi * 0.25 * (ox_max_od**2))
        self.ox_tank_mass = self.ox_length * ox_mass_per_length
        self.ox_density = ox_density
        self.ox_max_od = ox_max_od

        self.copv_length = copv_length
        self.copv_mass = copv_mass

        self.grain_length = (init_fuel_mass/fuel_density)/((math.pi/4)*(cc_max_od**2 - port_diameter**2))
        self.cc_cs_length = self.grain_length - self.cc_cs_length_offset
        if self.cc_cs_length <= 0:
            raise ValueError("Grain length is too short for the reference Chambersafe end allowance.")
        self.cc_al_mass = self.grain_length * self.cc_al_mass_per_length + self.cc_al_reference_offset
        self.cc_cs_mass = self.cc_cs_length * self.cc_cs_mass_per_length
        self.cc_shell_mass = self.cc_al_mass + self.cc_cs_mass
        #self.grain_length = 0.531495
        self.fuel_cg = self.grain_length / 2
        self.cc_length = self.upper_cc_comp.length + self.grain_length + self.lower_cc_comp.length + self.nozzle_comp.length
        #+ precombustor_length + postcombustor_length
        self.cc_mass = self.cc_shell_mass + self.upper_cc_comp.mass + self.lower_cc_comp.mass + self.nozzle_comp.mass
        self.fuel_density = fuel_density

        # After ingesting all relevant values, now finding the absolute coordinates of the center of each FIXED mass component

        #weighted average
        shell_cg_abs = self.nozzle_comp.length + self.lower_cc_comp.length + (self.grain_length / 2)
        shell_mass = self.cc_shell_mass

        upper_cg_offset_from_grain_top = self.upper_cc_comp.local_cg - (
            UPPER_CC_CG_REFERENCE_NOZZLE_LENGTH
            + UPPER_CC_CG_REFERENCE_LOWER_LENGTH
            + UPPER_CC_CG_REFERENCE_GRAIN_LENGTH
        )
        self.upper_cc_cg_abs = (
            self.nozzle_comp.length + self.lower_cc_comp.length
            + self.grain_length + upper_cg_offset_from_grain_top
        )
        # The lower chamber's existing ABS input was also measured with the
        # nominal nozzle; its local location follows a changed nozzle length.
        self.lower_cc_cg_abs = (
            self.lower_cc_comp.local_cg
            + self.nozzle_comp.length - UPPER_CC_CG_REFERENCE_NOZZLE_LENGTH
        )

        self.cc_cg_abs = ((self.upper_cc_cg_abs * self.upper_cc_comp.mass) +
                  (self.lower_cc_cg_abs * self.lower_cc_comp.mass) +
                  (self.nozzle_comp.local_cg * self.nozzle_comp.mass) + 
                  (shell_cg_abs * shell_mass)) / self.cc_mass
        #self.cc_cg_abs = ((self.upper_cc_comp.local_cg * self.upper_cc_comp.mass) + (self.lower_cc_comp.local_cg * self.lower_cc_comp.mass) + (self.nozzle_comp.local_cg * self.nozzle_comp.mass) + ((self.grain_length/2) * (self.grain_length * self.cc_mass_per_length)))/(self.cc_mass)
        #offset from top of cc
        self.interstage_cc_ox_cg_abs = self.lower_cc_comp.length + self.upper_cc_comp.length + self.nozzle_comp.length + self.grain_length + self.interstage_cc_ox_comp.local_cg
        self.ox_cg_abs = self.cc_length + self.interstage_cc_ox_comp.length + self.ox_length/2
        self.interstage_ox_copv_cg_abs = self.cc_length + self.interstage_cc_ox_comp.length + self.ox_length + self.interstage_ox_copv_comp.local_cg
        self.copv_cg_abs = self.cc_length + self.interstage_cc_ox_comp.length + self.ox_length + self.interstage_ox_copv_comp.length + self.copv_length/2

        # print ("self.cc_cg_abs: ", self.cc_cg_abs)
        # print ("self.interstage_cc_ox_cg_abs: ", self.interstage_cc_ox_cg_abs)
        # print ("self.ox_cg_abs: ", self.ox_cg_abs)
        # print ("self.interstage_ox_copv_cg_abs: ", self.interstage_ox_copv_cg_abs)
        # print ("self.copv_cg_abs: ", self.copv_cg_abs)

        # Then find the overall length and overall dry mass, then find the overall dry cg

        self.overall_length = self.cc_length + self.interstage_cc_ox_comp.length + self.ox_length + self.interstage_ox_copv_comp.length + self.copv_length
        self.dry_mass = self.cc_mass + self.interstage_cc_ox_comp.mass + self.ox_tank_mass + self.interstage_ox_copv_comp.mass + self.copv_mass
        print("Upper CC Mass: ", self.upper_cc_comp.mass)
        print("Upper CC CG from nozzle exit: ", self.upper_cc_cg_abs, "m")
        print("Lower CC CG from nozzle exit: ", self.lower_cc_cg_abs, "m")
        print ("Lower CC Mass: ", self.lower_cc_comp.mass)
        print ("CC Mass: ", self.cc_mass)
        print("CC Mass per Length: ", self.cc_mass_per_length)
        print("Ox Length: ", self.ox_length)
        self.overall_dry_abs_cg = (self.cc_mass * self.cc_cg_abs + self.interstage_cc_ox_comp.mass * self.interstage_cc_ox_cg_abs + self.ox_tank_mass * self.ox_cg_abs + self.interstage_ox_copv_comp.mass * self.interstage_ox_copv_cg_abs + self.copv_mass * self.copv_cg_abs)/self.dry_mass
        self.overall_dry_abs_cg_m = self.overall_dry_abs_cg * self.dry_mass

        self.overall_wet_abs_cg, self.wet_mass = self.current_cg_wet_mass (init_ox_mass, init_fuel_mass, init_press_mass)

        # print ("self.overall_length: ", self.overall_length)
        # print ("self.dry_mass: ", self.dry_mass)
        # print ("self.overall_dry_abs_cg: ", self.overall_dry_abs_cg)

    def get_cc_volume (self, port_diameter):
        return ((self.precombustor_length + self.postcombustor_length) * math.pi/4 * self.cc_max_od**2) + self.grain_length * math.pi/4 * port_diameter**2

    def ox_column_height (self, ox_mass):
        ox_volume = ox_mass / self.ox_density
        ox_column_height = (4 * ox_volume) / (math.pi * self.ox_max_od**2)
        return ox_column_height
    
    def pressurant_vol (self, ox_mass):
        return self.ox_tank_vol - 0.25 * math.pi * self.ox_column_height(ox_mass) * self.ox_max_od**2
    
    def ox_cg (self, ox_mass):
        return 0.5 * self.ox_column_height (ox_mass)
    
    def press_cg (self):
        return 0.5 * (self.ox_length - self.ox_column_height)
    
    def get_initWt_initLen (self):
        return self.dry_mass, self.overall_length

    def current_cg_wet_mass (self, ox_mass, fuel_mass, press_mass):
        ### [CHANGE FOR ADDITIONAL MASS COMPONENTS]
        ox_cg_m = ox_mass * (self.cc_length + self.interstage_cc_ox_comp.length + self.ox_column_height (ox_mass)/2)
        press_cg_m = self.copv_cg_abs * press_mass
        fuel_cg_m = fuel_mass * ((self.lower_cc_comp.length + self.grain_length/2) + self.nozzle_comp.length)
        # before: fuel_cg_m = fuel_mass * (self.lower_cc_comp.length + self.postcombustor_length + self.grain_length/2)

        current_wet_mass = ox_mass + fuel_mass + press_mass + self.dry_mass
        current_cg = (ox_cg_m + press_cg_m + fuel_cg_m + self.overall_dry_abs_cg_m) / current_wet_mass

        return current_cg, current_wet_mass

    def mass_breakdown(self, ox_mass, fuel_mass, press_mass):
        """Return the exact components and moments used by current_cg_wet_mass.

        Axial coordinates use the nozzle exit as zero. This is for reporting,
        so it is deliberately not called during every simulation time step.
        """
        shell_mass = self.cc_shell_mass
        shell_cg = self.nozzle_comp.length + self.lower_cc_comp.length + self.grain_length / 2
        tank_bottom = self.cc_length + self.interstage_cc_ox_comp.length
        parts = [
            ("Chamber", "Nozzle", "Dry", self.nozzle_comp.mass, self.nozzle_comp.length, self.nozzle_comp.local_cg),
            ("Chamber", "Lower chamber", "Dry", self.lower_cc_comp.mass, self.lower_cc_comp.length, self.lower_cc_cg_abs),
            ("Chamber", "Al casing (grain section)", "Dry", self.cc_al_mass, self.grain_length, shell_cg),
            ("Chamber", "Chambersafe (grain section)", "Dry", self.cc_cs_mass, self.cc_cs_length, shell_cg),
            ("Chamber", "Upper chamber", "Dry", self.upper_cc_comp.mass, self.upper_cc_comp.length, self.upper_cc_cg_abs),
            ("Chamber", "Fuel", "Consumable", fuel_mass, self.grain_length, shell_cg),
            ("Interstage", "Chamber to tank (run valve + injector)", "Dry", self.interstage_cc_ox_comp.mass, self.interstage_cc_ox_comp.length, self.interstage_cc_ox_cg_abs),
            ("Oxidizer tank", "Tank structure", "Dry", self.ox_tank_mass, self.ox_length, self.ox_cg_abs),
            ("Oxidizer tank", "LOX", "Consumable", ox_mass, self.ox_column_height(ox_mass), tank_bottom + self.ox_column_height(ox_mass) / 2),
            ("Interstage", "Tank to COPV", "Dry", self.interstage_ox_copv_comp.mass, self.interstage_ox_copv_comp.length, self.interstage_ox_copv_cg_abs),
            ("COPV", "COPV structure", "Dry", self.copv_mass, self.copv_length, self.copv_cg_abs),
            ("COPV", "N2 in COPV (fixed CG assumption)", "Consumable", press_mass, self.copv_length, self.copv_cg_abs),
        ]
        rows = []
        for section, name, kind, mass, length, cg in parts:
            reference = ("CC" if name.startswith("Chamber to tank") else
                         "OX" if name == "Tank to COPV" else "ABS (nozzle exit)")
            rows.append({
                "Section": section, "Component": name, "Type": kind,
                "Mass (kg)": mass, "Mass (lb)": mass * 2.20462262185,
                "Length (m)": length, "Length (in)": length / 0.0254,
                "CG from nozzle exit (m)": cg, "CG from nozzle exit (in)": cg / 0.0254,
                "Moment (kg m)": mass * cg, "Input reference": reference,
            })
        return rows
    
    def print_mass_comp (self):

        print (" *** MASS PROPERTIES *** ")
        print ("Wet Mass: " + str (round (self.wet_mass, 4)) + " kg")
        print ("Dry Mass: " + str (round (self.dry_mass, 4)) + " kg")
        print ("Dry CG: " + str (round (self.overall_dry_abs_cg, 4)) + " m")
        print ("Wet CG: " + str (round (self.overall_wet_abs_cg, 4)) + " m")
        print ("Overall Length: " + str (round (self.overall_length, 4)) + " m")
        print ("     ----------------------------- ")
        print (" *** OXIDIZER TANK MASS PROPERTIES ***")
        print ("Ox Tank Mass: " + str (round (self.ox_tank_mass, 4)) + " kg")
        print ("Ox Tank Length: " + str (round (self.ox_length, 4)) + " m")
        # print ("Remaining Fuel: " + str (round (self.final_fuel_mass, 4)) + " kg")
        # print ("Final Port Diameter: " + str (round (self.final_port_diameter, 4)) + " m")
        print ("     ---------------------------------- ")
        print (" *** COMBUSTION CHAMBER MASS PROPERTIES *** ")
        print ("CC Shell Mass: " + str (round (self.cc_shell_mass, 4)) + " kg")
        print ("  Al casing mass: " + str (round (self.cc_al_mass, 4)) + " kg")
        print ("  Chambersafe mass: " + str (round (self.cc_cs_mass, 4)) + " kg")
        print ("CC Length: " + str (round (self.cc_length, 4)) + " m")
        print ("     ------------------ ")
        # print (" " + str (round (self.init_ox_mdot, 4)) + " kg/s")
        # print ("     ------------------ ")
        # print (" *** CHAMBER CONDITIONS *** ")
        # print ("Grain Length: " + str (round (self.grain_length, 4)) + " m")
        # print ("Initial Port Diameter: " + str (round (self.init_port_diameter, 4)) + " m")
        # print ("Max Port Mass Flux: " + str (round (self.init_ox_mdot/(0.25*math.pi*self.init_port_diameter**2), 4)) + " kg/m^2")
        # print ("Chamber Temperature: " + str (round(self.Tc, 4)) + " K")
        # print ("Throat Temperature: " + str (round(self.Tt, 4)) + " K")
        # print ("Exit Temperature: " + str (round (self.Te, 4)) + " K")
        # print ("     ----------- ")
        # print (" *** NOZZLE CONDITIONS *** ")
        # print ("Throat Diameter: " + str (round (self.throatDia, 4)) + " mm")
        # print ("Exit Diameter: " + str (round (self.exitDia, 4)) + " mm")
        # print ("Average Throat Mass Flux: " + str (round (sum(self.throat_mass_flux)/len(self.throat_mass_flux), 4)) + " kg/m^2")
        # print ("     ----------- ")
        # print (" *** PERFORMANCE ***")
        # print ("Average Thrust: " + str (round (self.avg_thrust, 4)) + " N")
        # print ("Max Thrust (N): " + str (round (max (self.thrust_curve), 4)) + " N")
        # print ("Max Thrust (lbf): " + str (round (UNIT.N_to_lbf (max (self.thrust_curve)), 4)) + " lbf")
        # print ("Burn Time: " + str (round (self.total_time, 4)) + " s")
        # print ("Average Thrust Coefficient: " + str (round (self.avg_coef, 4)))
        # print ("Total Impulse: " + str (round (self.total_impulse, 4)) + " Ns")
        # print ("Average ISP: " + str (round (self.avg_isp, 4)) + " s")

class part:

    def __init__ (self, mass, local_cg, length, reference):

        if reference != "ABS" and reference != "OX" and reference != "CC":
            raise Exception ("Please enter a mass reference with the ID 'OX', 'CC', or 'ABS'.")

        self.mass = mass
        self.local_cg = local_cg

        self.length = length
        self.abs_location = 0

        self.reference = reference
    
