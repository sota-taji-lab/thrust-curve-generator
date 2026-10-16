# Author: Aadam Awad

import xml.etree.ElementTree as ET
from xml.dom import minidom
import datetime
import os

class rse_file:

    def __init__ (self, t, f, m, cg, diam, length, initWt, propWt, delays, 
                  autoCalcMass, autoCalcCG, avgThrust, peakThrust, throatDia, exitDia, 
                  Itot, burn_time, massFrac, ISP, tDiv, tStep, tFix, FDiv, Fstep, FFix, 
                  mDiv, mStep, mFix, cgDiv, cgStep, cgFix):
        
        # Automatically generate the engine code
        if (10240 > Itot >= 5120.01):
            code_prefix = "M"
        elif (20480 > Itot >= 10240.01):
            code_prefix = "N"
        elif (40960 > Itot >= 20480.01):
            code_prefix = "O"
        elif (81920 > Itot >= 40960.01):
            code_prefix = "P"
        elif (163840 > Itot >= 81920.01):
            code_prefix = "Q"
        elif (327680 > Itot >= 163840.01):
            code_prefix = "R"
        elif (655360 > Itot >= 327680.01):
            code_prefix = "S"
        else:
            raise Exception ("Warning: the parameters defined exceed feasible motor parameters! Please adjust.")
        
        code = code_prefix + str (int (avgThrust))
        codeDisp = code_prefix + "-" + str (int (avgThrust))

        root = ET.Element ("engine-database")
        engine_list = ET.SubElement (root, "engine-list")

        print (initWt)
        print (propWt)

        engine_data = {

            "mfg": "Columbia Space Initiative Rockets Mission",
            "code": code,
            "Type": "hybrid",
            "dia": str (diam),
            "len": str (length),
            "initWt": str (initWt),
            "propWt": str (propWt),
            "delays": "",
            "auto-calc-mass": "0",
            "auto-calc-cg": "0",
            "avgThrust": str (avgThrust),
            "peakThrust": str (peakThrust),
            "throatDia": str (throatDia),
            "exitDia": str (exitDia),
            "Itot": str (Itot),
            "burn-time": str (burn_time),
            "massFrac": str (massFrac),
            "Isp": str (ISP),
            "tDiv": "10",
            "tStep": "-1.",
            "tFix": "1",
            "FDiv": "10",
            "FStep": "-1.",
            "FFix": "1",
            "mDiv": "10",
            "mStep": "-1.",
            "mFix":"1",
            "cgDiv": "10",
            "cgStep": "-1.",
            "cgFix": "1"
        }

        engine = ET.SubElement (engine_list, "engine", **engine_data)

        now = datetime.datetime.now()
        commentStr = "Columbia Space Initiative Rockets Mission custom script for parameterization and simulation of hybrid rocket motors. File generated on " + str (now)

        comments = ET.SubElement (engine, "comments")
        comments.text = commentStr

        data = ET.SubElement(engine, "data")

        itr = 0

        for i in range (len(t)):

            ET.SubElement (data, "eng-data", {"t":str(round(t[i], 4)), "f":str(round(f[i], 2)), "m":str(round(m[i], 4)), "cg":str(round(length - cg[i], 2))})

        # Convert the tree to a string
        xml_str = ET.tostring(root, encoding="utf-8")
        
        # Prettify the XML string
        pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="")

        # Remove the first line (<?xml version="1.0" ?>)
        pretty_xml = "\n".join(pretty_xml.split("\n")[1:])

        fileName = codeDisp + "_columbia-hybrid.rse"
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(script_dir + "/rse files", fileName)

        with open(filepath, "w") as f:
            f.write(pretty_xml)

'''
class parameters_file:

    def __init__ (self, diam, length, initWt, propWt, avgThrust, peakThrust, throatDia, exitDia, Itot, burn_time, massFrac, ISP):

        fileName = "engine_parameters.txt"
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(script_dir + "/parameters files", fileName)

        with open(filepath, "w") as f:
            f.write ("Diameter (m): " + str (diam) + "\n")
            f.write ("Length (m): " + str (length) + "\n")
            f.write ("Initial Weight (kg): " + str (initWt) + "\n")
            f.write ("Propellant Weight (kg): " + str (propWt) + "\n")
            f.write ("Average Thrust (N): " + str (avgThrust) + "\n")
            f.write ("Peak Thrust (N): " + str (peakThrust) + "\n")
            f.write ("Throat Diameter (m): " + str (throatDia) + "\n")
            f.write ("Exit Diameter (m): " + str (exitDia) + "\n")
            f.write ("Total Impulse (Ns): " + str (Itot) + "\n")
            f.write ("Burn Time (s): " + str (burn_time) + "\n")
            f.write ("Mass Fraction: " + str (massFrac) + "\n")
            f.write ("Average ISP: " + str (ISP) + "\n")'''