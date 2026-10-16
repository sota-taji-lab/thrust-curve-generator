# Author: Aadam Awad

import os
import socket
import math
import pandas as pd
import numpy as np
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

class lox_paraffin:

    def get_params_fixedPc_fixedOF (self, Pc, OF):

        temp = 3000
        gamma = 1.2
        molecular_mass = 10
        characteristic_velocity = 1600
        
        return temp, gamma, molecular_mass, characteristic_velocity

class nitrous_paraffin:

    def get_params_fixedPc_fixedOF (self, Pc, OF):

        temp = 3000
        gamma = 1.1
        molecular_mass = 10
        characteristic_velocity = 1600
        
        return temp, gamma, molecular_mass, characteristic_velocity