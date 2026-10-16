# Author: Aadam Awad

import math

class unit:

    def psig_To_Pa (self, psig):
        return psig * 6894.76 + 101352.9

    def barA_To_Pa (self, barA):
        return barA / 100000
    
    def Pa_to_psig (self, Pa):
        return (Pa - 101352.9) / 6894.76
    
    def Pa_to_psia (self, Pa):
        return Pa / 6894.76
    
    def N_to_lbf (self, n):
        return n * 0.224809
    
    def in_to_m (self, inch):
        return inch * 0.0254
    