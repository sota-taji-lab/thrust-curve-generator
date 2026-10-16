import CoolProp.CoolProp as cp

class prop:

    def __init__ (self, fuel_ID, ox_ID, ox_pvap):

        if fuel_ID == 'HTPB' and ox_ID == 'LOX':
            self.a = 3.043E-2 # src: Waxman Table 1.1
            self.n = 0.681 # src: Waxman Table 1.1

            self.fuel_density = 920 # kg/m^3, src: https://www.researchgate.net/figure/Formulation-of-propellant-A-The-density-of-cured-HTPB-is-920-kg-m-3_tbl1_279252447#:~:text=The%20density%20of%20cured%20HTPB%20is%20920%20kg%2Fm%203%20.
            self.ox_density = cp.PropsSI ('D','P', ox_pvap,'Q',0,'Oxygen') # kg/m^3

        elif fuel_ID == 'HDPE' and ox_ID == 'LOX':
            self.a = 2.340E-02 # src: Waxman Table 1.1
            self.n = 0.62 # src: Waxman Table 1.1

            self.fuel_density = 950 # kg/m^3, src: https://en.wikipedia.org/wiki/High-density_polyethylene
            self.ox_density = cp.PropsSI ('D','P', ox_pvap,'Q',0,'Oxygen') # kg/m^3

        elif fuel_ID == 'PARAFFIN' and ox_ID == 'LOX':
            # self.a = 11.70E-2 # src: Waxman Table 1.1 [Overridden]
            self.a = 1 * 11.70E-2 # src: Guess for regression with aluminum
            self.n = 0.62 # src: Waxman Table 1.1

            self.fuel_density = 900 # kg/m^3 src: https://web.archive.org/web/20080311173419/http://www.kayelaby.npl.co.uk/general_physics/2_2/2_2_1.html +  aluminum doping #Al doping removed
            self.ox_density = cp.PropsSI ('D','P', ox_pvap,'Q',0,'Oxygen') # kg/m^3

        elif fuel_ID == 'PARAFFIN' and ox_ID == 'N2O':
            self.a = 15.50E-2 # src: Waxman Table 1.1
            self.n = 0.50 # src: Waxman Table 1.1

            self.fuel_density = 900 # kg/m^3 src: https://web.archive.org/web/20080311173419/http://www.kayelaby.npl.co.uk/general_physics/2_2/2_2_1.html
            self.ox_density = cp.PropsSI ('D','P', ox_pvap,'Q',0,'Nitrous Oxide') # kg/m^3
            
        else:
            raise Exception ('Please enter a valid propellant combination. The script currently support LOX/HTPB, LOX/HDPE, LOX/PARAFFIN, and LOX/N2O.')
        
class press:

    def __init__ (self, press_ID):

        if press_ID == 'Nitrogen':
            self.molec_mass = 0.02802 # kg/mol

        elif press_ID == 'Helium':
            self.molec_mass = 0.004002602 # kg/mol

        else:
            raise Exception ('Please enter a valid pressurant gas. The script currently support Nitrogen (N2) and Helium (H2)')