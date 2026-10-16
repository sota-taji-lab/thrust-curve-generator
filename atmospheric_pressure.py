# Author: Aadam Awad
# This model was developed based on the International Standard Atmosphere. It can be found here:
# http://fisicaatmo.at.fcen.uba.ar/practicas/ISAweb.pdf

import os
import glob
import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

STANDARD_PRESSURE = 101325 # Pa
STANDARD_TEMPERATURE = 298.15 # K

class atmo:

    def __init__ (self):

        # Resolve the flight-data folder relative to this source file.
        script_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(script_dir, "csv files")
        csv_files = glob.glob(os.path.join(csv_path, '*.csv'))

        if not os.path.exists (csv_path):
            raise Exception ("Invalid file path")
        if not csv_files:
            raise Exception ("No CSV files found in the specified folder: " + str (csv_files))
        else:
            latest_file = max(csv_files, key=os.path.getmtime)
            print(f"Reading the most recent CSV file: {latest_file}")

        data = pd.read_csv(latest_file)
        
        # print(data.head())  # Display the first few rows of the data
        data.columns = ['Time_s', 'Accel_G', 'Air_pressure_mbar']
        filtered_data = data [data ['Accel_G'] > 0]

        time = filtered_data ['Time_s']
        air_pressure_mbar = filtered_data ['Air_pressure_mbar']

        poly_coef = np.polyfit (time, air_pressure_mbar, 12)
        self.poly_model = np.poly1d (poly_coef)

    def air_pressure (self, time):

        # if altitude < 11000:
        #     t = STANDARD_TEMPERATURE - 6.5*altitude/1000 # ISA Eqn 1
        # elif 20000 < altitude <= 11000:
        #     t = 216.65
        # else:
        #     raise Exception ("Altitude has exceeded thermal model")
        
        # p = STANDARD_PRESSURE * (1 - 0.0065 * altitude/t)**5.2561

        # if p <= 0:
        #     raise Exception ('Atmospheric pressure is below 0')
        
        # return p
        # print (100 * self.poly_model (time))
        return 100 * self.poly_model (time)

        
