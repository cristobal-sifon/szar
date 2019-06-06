#Python 2 compatibility stuff
from __future__ import print_function
from __future__ import division
from builtins import str
from builtins import range
from six.moves import configparser
import six
if six.PY2:
  ConfigParser = configparser.SafeConfigParser
else:
  ConfigParser = configparser.ConfigParser

#cosmo imports
from orphics.io import dict_from_section, list_from_config
import numpy as np
from szar.derivatives import Derivs_Clustering

# etc
import argparse
import time
import sys

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", "--expname", help="name of experiment", default='S4-1.0-CDT')
    parser.add_argument("-g", "--gridname", help="name of grid", default='grid-owl2')
    parser.add_argument("-v", "--version", help="version number", default='0.6')
    parser.add_argument('-p', '--params', help='parameters to include in the derivative calculation', type=str, default='allParams')
    parser.add_argument('-i', '--inifile', help='initialization file for pipeline parameters', type=str, default='input/pipeline.ini')
    args = parser.parse_args()

    DIR = "userdata/"
    FISH_FAC_NAME = "fish_factor"
    FISH_DERIV_NAME = "fish_derivs"
    UPNAME = "psups"
    DOWNNAME = "psdowns"
    STEPNAME = "steps"
    PARAMSNAME = "params"
    currenttime = time.strftime("%Y-%m-%d-%H-%M-%S-%Z", time.localtime())

    deriv = Derivs_Clustering(args.inifile, args.expname, args.gridname, args.version)

    selected_params = args.params.replace(' ', '').split(',')

    if "allParams" in selected_params:
        if len(selected_params) != 1:
            print("Please don't select more than allParams... It's greedy.")
            sys.exit()

        deriv.instantiate_params()
    else:
        deriv.instantiate_params(selected_params)

    deriv.instantiate_grids()

    fish_derivs, fish_facs, ups, downs = deriv.make_derivs()

    np.save(DIR + deriv.saveid + '_' + FISH_FAC_NAME + '_' + currenttime, fish_facs)
    np.save(DIR + deriv.saveid + '_' + FISH_DERIV_NAME + '_' + currenttime, fish_derivs)
    np.save(DIR + deriv.saveid + '_' + UPNAME + '_' + currenttime, ups)
    np.save(DIR + deriv.saveid + '_' + DOWNNAME + '_' + currenttime, downs)
    np.save(DIR + deriv.saveid + '_' + STEPNAME + '_' + currenttime, deriv.steps)
    np.save(DIR + deriv.saveid + '_' + PARAMSNAME + '_' + currenttime, deriv.fisher_params)
