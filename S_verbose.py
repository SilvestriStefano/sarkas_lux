'''
S_verbose.py
printout Version info & simulation progess
'''
import numpy as np
from inspect import currentframe, getframeinfo
import time
import S_constants as const

class Verbose:
    def __init__(self, params):
        print("Sarkas Ver. 1.0")
        self.params = params

    def sim_setting_summary(self):
        params = self.params
        print('\n\n----------- Molecular Dynamics Simulation ----------------------')
        print("units: ", params.units)
        print("Potential: ", params.Potential.type)
        if (params.Potential.type == "Yukawa"):
            print('kappa = ', params.Potential.matrix[0, 0, 0]*params.ai)
            print('Gamma = ', params.Potential.matrix[1, 0, 0])
            if (params.Potential.method == "P3M"):
                print('grid_size * Ewald_parameter (h * alpha) = ', params.hx*params.P3M.G_ew)

            if (params.Potential.type == "Yukawa" and params.num_species == 1):
                print("ion plasma frequency [s^(-1)] = ", params.wp)

        print('Temperature [K] = ', params.Ti)
        print('No. of particles = ', params.total_num_ptcls)
        print('Box length along x axis = ', params.Lv[0])
        print('Box length along y axis = ', params.Lv[1])
        print('Box length along z axis = ', params.Lv[2])
        print("ion sphere radius = ", params.ai)
        print("rcut/a_ws = ", params.Potential.rc/params.ai)
        print('No. of non-zero box dimensions = ', params.d)
        print('time step = ', 1.0/(params.Control.dt) ) 
        print('No. of equilibration steps = ', params.Control.Neq)
        print('No. of post-equilibration steps = ', params.Control.Nt)
        print('snapshot interval = ', params.Control.dump_step)
        print('Periodic boundary condition{1=yes, 0=no} =', params.Control.PBC)
        if (params.Langevin.on):
            print("Langevin model = ", params.Langevin.type)

        print('smallest interval in Fourier space for S(q,w): qa_min = ', 2*np.pi*params.ai/params.Lx)


    def time_stamp(self, time_stamp):
        t = time_stamp
        print('Time for initialization = ', t[2]-t[1])
        print('Time for equilibration = ', t[3]-t[2])
        print('Time for production = ', t[4]-t[3])
        print('Total elapsed time = ', t[4]-t[0])
