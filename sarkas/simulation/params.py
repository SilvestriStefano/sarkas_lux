"""
Module for handling Params class
"""
import yaml
import numpy as np
import os.path
import sys
import scipy.constants as const


class Params:
    """
    Simulation's Parameters.
    
    Attributes
    ----------
    aws : float
        Wigner-Seitz radius. Calculated from the ``total_num_density`` .

    box_volume : float
        Box volume.

    dimensions : int
        Number of non-zero dimensions.

    fourpie0: float
        Electrostatic constant :math: `4\pi \espilon_0`.

    species : list
        List of Species objects with species' information.

    load_method : str
        Particles loading described in Species.

    load_rand_seed : int
        Seed of random number generator.

    load_restart_step : int
        Restart time step.

    load_r_reject : float
        Rejection radius to avoid placing particles to close to each other.

    load_perturb : float
        Strength of initial perturbation.

    load_halton_bases : array, shape(3)
        Array of 3 ints each of which is a base for the Halton sequence.

    num_species : int
        Number of species.

    kB : float
        Boltzmann constant obtained from ``scipy.constants``.

    hbar : float
        Reduced Planck's constant.

    hbar2 : float
        Square of reduced Planck's constant.

    a0 : float
        Bohr Radius.

    c0 : float
        Speed of light.

    qe : float
        Elementary charge.

    me : float
        Electron mass.

    eps0 : float
        Vacuum electrical permittivity.

    eV2K : float
        Conversion factor from eV to Kelvin obtained from ``scipy.constants``.

    J2erg : float
        Conversion factor from Joules to erg. Needed for cgs units.

    QFactor : float
        Charge Factor defined as :math:`\mathcal Q = \sum_{i}^{N} q_{i}^2` .

    L : float
        Smallest box length.

    Lx : float
        Box length in the :math:`x` direction.

    Ly : float
        Box length in the :math:`y` direction.

    Lz : float
        Box length in the :math:`z` direction.

    Lv : array, shape(3)
        Box length in each direction.

    e1 : float
        Unit vector in the :math:`x` direction.

    e2 : float
        Unit vector in the :math:`y` direction.

    e3 : float
        Unit vector in the :math:`z` direction.

    N : int
        Total number of particles same as ``tot_num_ptcls``.

    ptcls_input_file : str
        User defined input file containing particles' data.

    input_file : str
        YAML Input file with all the simulation's parameters.

    Te : float
        Equilibrium electron temperature. Defined in Potential module.

    Ti : float
        Total Equilibrium Ion temperature.

    T_desired : float
        Equilibrium temperature.

    tot_net_charge : float
        Total charge in the system.

    total_num_density : float
        Total number density. Calculated from the sum of ``Species.num_density``.

    total_num_ptcls : int
        Total number of particles. Calculated from the sum of ``Species.num``.

    wp : float
        Total Plasma frequency. Defined in Potential module.

    force : func
        Function for force calculation. Assigned in Potential module.
    """

    def __init__(self):
        # Container of Species
        self.ne = 0.0
        self.L = 0.0
        self.Lv = []
        self.input_file = None
        self.box_volume = 0.0
        self.dimensions = 3
        self.J2erg = 1.0e+7  # erg/J
        self.eps0 = const.epsilon_0
        self.fourpie0 = 4.0 * np.pi * self.eps0
        self.me = const.physical_constants["electron mass"][0]
        self.qe = const.physical_constants["elementary charge"][0]
        self.hbar = const.hbar
        self.hbar2 = self.hbar ** 2
        self.c0 = const.physical_constants["speed of light in vacuum"][0]
        self.eV2K = const.physical_constants["electron volt-kelvin relationship"][0]
        self.eV2J = const.physical_constants["electron volt-joule relationship"][0]
        self.a0 = const.physical_constants["Bohr radius"][0]
        self.kB = const.Boltzmann
        self.aws = 0.0
        self.tot_net_charge = 0.0
        self.QFactor = 0.0
        self.num_species = 1
        self.Ti = 0.0
        self.T_desired = 0.0
        self.total_num_density = 0
        self.total_num_ptcls = 0
        self.species = []
        #
        self.pppm = self.P3M()
        self.BC = self.BC()
        self.Magnetic = self.Magnetic()
        self.potential = self.Potential()
        self.integrator = self.Integrator()
        self.control = self.Control()
        self.thermostat = self.Thermostat()
        self.Langevin = self.Langevin()
        self.PostProcessing = self.PostProcessing()

    class BC:
        """Boundary Conditions.

        Attributes
        ----------
        pbc_axes : list
            Axes with Periodic Boundary Conditions.

        mm_axes : list
            Axes with Momentum Mirror Conditions.

        open_axes: list
            Axes with Open Boundary Conditions.

        pbc_axes_indx : array
            Indexes of axes with Periodic Boundary Conditions.

        mm_axes_indx : array
            Indexes of axes with Momentum Mirror Conditions.

        open_axes_indx: array
            Indexes of axes with Open Boundary Conditions.
        """

        def __init__(self):
            self.pbc_axes = []
            self.mm_axes = []
            self.open_axes = []
            self.pbc_axes_indx = []
            self.mm_axes_indx = []
            self.open_axes_indx = []

    class Species:
        """ 
        Particle Species.

        Attributes
        ----------
            name : str
                Species' name.

            number_density : float
                Species number density in appropriate units.

            num : int
                Number of particles of Species.

            mass : float
                Species' mass.

            charge : float
                Species' charge.

            Z : float
                Species charge number.
            
            atomic_weight : float
                Species atomic weight.

            init_vel: array
                Initial velocity in x,y,z directions.
        """

        def __init__(self):
            pass

    class Magnetic:
        """ 
        Parameters for a plasma in a constant magnetic field

        Attributes
        ----------
        on : bool
            Flag for magnetized plasma.

        elec_therm : int
            Thermalize electrostatic forces first?
            0 = False, 1 = True (default).

        Neq_mag : int
            Number of equilibration steps with magnetic field on.

        Bfield : float
            Strength of Magnetic Field.
        """

        def __init__(self):
            self.on = False
            self.elec_therm = True
            self.Neq_mag = 10000
            self.BField = 0.0

    class Potential:
        """
        Parameters specific to potential choice.

        Attributes
        ----------
        matrix : array
            Potential's parameters.

        method : str
            Algorithm to use for force calculations.
            "PP" = Linked Cell List (default).
            "P3M" = Particle-Particle Particle-Mesh.

        rc : float
            Cutoff radius.

        type : str
            Interaction potential: LJ, Yukawa, EGS, Coulomb, QSP, Moliere.

        """

        def __init__(self):
            self.method = "PP"

    class P3M:
        """ 
        P3M Algorithm parameters.

        Attributes
        ----------
        aliases : array, shape(3)
            Number of aliases in each direction.

        cao : int
            Charge assignment order.

        on : bool
            Flag.

        MGrid : array, shape(3), int
            Number of mesh point in each direction.

        Mx : int
            Number of mesh point along the :math:`x` axis.

        My : int
            Number of mesh point along the :math:`y` axis.

        Mz : int
            Number of mesh point along the :math:`z` axis.

        mx_max : int
            Number of aliases along the reciprocal :math:`x` direction.

        my_max : int
            Number of aliases along the reciprocal :math:`y` direction.

        mz_max : int
            Number of aliases along the reciprocal :math:`z` direction.

        G_ew : float
            Ewald parameter.

        G_k : array
            Optimized Green's function.

        hx : float
            Mesh spacing in :math:`x` direction.

        hy : float
            Mesh spacing in :math:`y` direction.

        hz : float
            Mesh spacing in :math:`z` direction.

        PP_err : float
            Force error due to short range cutoff.

        PM_err : float
            Force error due to long range cutoff.

        F_err : float
            Total force error.

        kx_v : array
            Array of :math:`k_x` values.

        ky_v : array
            Array of :math:`k_y` values.

        kz_v : array
            Array of :math:`k_z` values.

        """

        def __init__(self):
            self.on = False

    class Integrator:
        """
        Integrator's parameters.

        Attributes
        ----------
            type : str
                Integrator type. 
        """

        def __init__(self):
            pass

    class Thermostat:
        """
        Thermostat's parameters

        Attributes
        ----------
            on : int
                Flag. 1 = True, 0 = False.

            type : int
                Berendsen only.

            tau : float
                Berendsen parameter :math:`\tau`.

            timestep : int
                Number of timesteps to wait before turning on Berendsen.
                (default) = 0
        """

        def __init__(self):
            self.on = 0
            self.timestep = 0

    class Langevin:
        """
        Parameters for Langevin Dynamics.

        Attributes
        ----------
            on : int
                Flag. 0 = False, 1 = True.

            type : str
                Type of Langevin. 

            gamma : float
                Langeving gamma.
        """

        def __init__(self):
            self.on = 0

    class Control:
        """
        General simulation parameters

        Attributes
        ----------
            units : str
                cgs or mks.

            dt : float
                timestep. Same as ``Params.dt``.

            Nsteps : int
                Number of simulation timesteps.

            BC : str
                Boundary Condition. 'Periodic' only.

            dump_step : int
                Production Snapshot interval.

            therm_dump_step : int
                Thermalization Snapshot interval.

            np_per_side : array
                Number of particles per box length. Default= :math: `N_{tot}^{1/3}`
                Note that :math: `N_x x N_y x N_z = N_{tot}`

            writexyz : str
                Flag for XYZ file for OVITO. Default = False.

            verbose : str
                Flag for verbose screen output.
            
            checkpoint_dir : str
                Path to the directory where the outputs of the current simulation will be stored.
                Default = "Simulations/UnNamedRun"

            log_file : str
                File name for log output. Default = log.out

            pre_run : bool
                Flag for initial estimation of simulation parameters.

            simulations_dir : str
                Path to the directory where all future simulations will be stored. Default = cwd +  "Simulations"

            dump_dir : str
                Path to the directory where simulations' dumps will be stored.
                Default = "Simulations/UnNamedRun/Production"

            therm_dir : str
                Path to the directory where simulations' dumps will be stored.
                Default = "Simulations/UnNamedRun/Thermalization"

        """

        def __init__(self):
            self.units = None
            self.measure = False
            self.dt = None
            self.Nsteps = None
            self.Neq = None
            self.dump_step = 1
            self.therm_dump_step = 1
            self.writexyz = False
            self.verbose = True
            self.simulations_dir = "Simulations"
            self.job_dir = None
            self.production_dir = None
            self.equilibration_dir = None
            self.preprocessing_dir = "PreProcessing"
            self.postprocessing_dir = "PostProcessing"
            self.job_id = None
            self.log_file = None
            self.np_per_side = []
            self.pre_run = False

    class PostProcessing:

        def __init__(self):
            self.rdf_nbins = 100
            self.ssf_no_ka_values = np.array([5, 5, 5], dtype=int)
            self.dsf_no_ka_values = np.array([5, 5, 5], dtype=int)
            self.hermite_order = 10

    def setup(self, args):
        """
        Setup simulations' parameters.

        Parameters
        ----------
        args : dict
            Input arguments
        """
        self.input_file = args["input_file"]

        # Parse parameters from input file
        self.common_parser(self.input_file)
        self.create_directories(args)
        self.assign_attributes()
        self.from_input_dict(args)
        self.control.verbose = args["verbose"]
        # Coulomb potential
        if self.potential.type == "Coulomb":
            from sarkas.potentials import coulomb as Coulomb
            Coulomb.setup(self)

        # Yukawa potential
        if self.potential.type == "Yukawa":
            from sarkas.potentials import yukawa as Yukawa
            Yukawa.setup(self)

        # exact gradient-corrected screening (EGS) potential
        if self.potential.type == "EGS":
            from sarkas.potentials import egs as EGS
            EGS.setup(self)

        # Lennard-Jones potential
        if self.potential.type == "LJ":
            from sarkas.potentials import lennardjones612 as LJ
            LJ.setup(self)

        # Moliere potential
        if self.potential.type == "Moliere":
            from sarkas.potentials import moliere as Moliere
            Moliere.setup(self)

        # QSP potential
        if self.potential.type == "QSP":
            from sarkas.potentials import qsp as QSP
            QSP.setup(self)

        return

    def common_parser(self, filename):
        """
        Parse common parameters from input file

        Parameters
        ----------
        filename : str
            Input file's name.

        """
        self.input_file = filename

        with open(filename, 'r') as stream:
            dics = yaml.load(stream, Loader=yaml.FullLoader)

            for lkey in dics:
                if lkey == "Particles":
                    for keyword in dics[lkey]:
                        for key, value in keyword.items():

                            if key == "species":
                                spec = self.Species()
                                self.species.append(spec)
                                ic = len(self.species) - 1

                                for key, value in value.items():
                                    if key == "name":
                                        self.species[ic].name = value

                                    if key == "number_density":
                                        self.species[ic].num_density = float(value)
                                        self.total_num_density += self.species[ic].num_density

                                    if key == "mass":
                                        self.species[ic].mass = float(value)

                                    if key == "num":
                                        self.species[ic].num = int(value)
                                        self.total_num_ptcls += int(self.species[ic].num)

                                    if key == "Z":
                                        self.species[ic].Z = float(value)

                                    if key == "temperature":
                                        self.species[ic].temperature = float(value)

                                    if key == "A":
                                        self.species[ic].atomic_weight = float(value)

                                    if key == 'initial_velocity':
                                        self.species[ic].init_vel = np.array(value)

                                    if key == "mass_density":
                                        self.species[ic].mass_density = float(value)

                                    if key == "temperature_eV":
                                        self.species[ic].temperature = float(value) * self.eV2K

                            if key == "load":
                                for key, value in value.items():
                                    if key == "method":
                                        self.load_method = value

                                    if key == 'restart_step':
                                        self.load_restart_step = int(value)

                                    if key == 'therm_restart_step':
                                        self.load_therm_restart_step = int(value)

                                    if key == 'r_reject':
                                        self.load_r_reject = float(value)

                                    if key == 'perturb':
                                        self.load_perturb = float(value)

                                    if key == 'halton_bases':
                                        self.load_halton_bases = np.array(value)

                                    if key == 'particle_input_file':
                                        self.ptcls_input_file = value

                if lkey == "Potential":
                    for keyword in dics[lkey]:
                        for key, value in keyword.items():
                            if key == "type":
                                self.potential.type = value

                            if key == "method":
                                self.potential.method = value

                            if key == "rc":
                                self.potential.rc = float(value)

                if lkey == "P3M":
                    self.pppm.on = True
                    for keyword in dics[lkey]:
                        for key, value in keyword.items():
                            if key == "MGrid":
                                self.pppm.MGrid = np.array(value)
                                self.pppm.Mx = self.pppm.MGrid[0]
                                self.pppm.My = self.pppm.MGrid[1]
                                self.pppm.Mz = self.pppm.MGrid[2]
                            if key == "cao":
                                self.pppm.cao = int(value)
                            if key == "aliases":
                                self.pppm.aliases = np.array(value, dtype=int)
                                self.pppm.mx_max = self.pppm.aliases[0]
                                self.pppm.my_max = self.pppm.aliases[1]
                                self.pppm.mz_max = self.pppm.aliases[2]
                            if key == "alpha_ewald":
                                self.pppm.G_ew = float(value)

                if lkey == "Thermostat":
                    self.thermostat.on = 1
                    for keyword in dics[lkey]:
                        for key, value in keyword.items():
                            if key == 'type':
                                self.thermostat.type = value

                            # If Berendsen
                            if key == 'tau':
                                if float(value) > 0.0:
                                    self.thermostat.tau = float(value)
                                else:
                                    print("\nBerendsen tau parameter must be positive")
                                    sys.exit()

                            if key == 'timestep':
                                # Number of timesteps to wait before turning on Berendsen
                                self.thermostat.timestep = int(value)

                            if key == "temperatures_eV":
                                if isinstance(value, list):
                                    self.thermostat.temperatures = np.array(value, dtype=float)
                                else:
                                    self.thermostat.temperatures = np.array([value], dtype=float)
                                self.thermostat.temperatures *= self.eV2K

                            if key == "temperatures":
                                # Conversion factor from eV to Kelvin
                                if isinstance(value, list):
                                    self.thermostat.temperatures = np.array(value, dtype=float)
                                else:
                                    self.thermostat.temperatures = np.array([value], dtype=float)

                if lkey == "Magnetized":
                    self.Magnetic.on = True
                    for keyword in dics[lkey]:
                        for key, value in keyword.items():
                            if key == "B_Gauss":
                                G2T = 1e-4
                                self.Magnetic.BField = float(value) * G2T

                            if key == "B_Tesla":
                                self.Magnetic.BField = float(value)

                            if key == "electrostatic_thermalization":
                                # 1 = true, 0 = false
                                self.Magnetic.elec_therm = value

                            if key == "Neq_mag":
                                # Number of equilibration of magnetic degrees of freedom
                                self.Magnetic.Neq_mag = int(value)

                if lkey == "Integrator":
                    for keyword in dics[lkey]:
                        for key, value in keyword.items():
                            if key == 'type':
                                self.integrator.type = value

                if lkey == "Langevin":
                    self.Langevin.on = 1
                    for keyword in dics[lkey]:
                        for key, value in keyword.items():
                            if key == 'type':
                                self.Langevin.type = value
                            if key == 'gamma':
                                self.Langevin.gamma = float(value)

                if lkey == "PostProcessing":
                    for keyword in dics[lkey]:
                        for key, value in keyword.items():
                            if key == 'rdf_nbins':
                                self.PostProcessing.rdf_nbins = int(value)
                            if key == 'ssf_no_ka_values':
                                self.PostProcessing.ssf_no_ka_values = value
                            if key == 'dsf_no_ka_values':
                                self.PostProcessing.dsf_no_ka_values = value

                if lkey == "BoundaryConditions":
                    for keyword in dics[lkey]:
                        for key, value in keyword.items():
                            if key == "periodic":
                                self.BC.pbc_axes = value

                            if key == "momentum_mirror":
                                self.BC.mm_axes = value

                            if key == "open":
                                self.BC.open_axes = value

                if lkey == "Control":
                    for keyword in dics[lkey]:
                        for key, value in keyword.items():
                            # Units
                            if key == "units":
                                self.control.units = value

                            # timestep
                            if key == "dt":
                                self.control.dt = float(value)

                            # Number of simulation timesteps    
                            if key == "Nsteps":
                                self.control.Nsteps = int(value)

                            # Number of equilibration timesteps
                            if key == "Neq":
                                self.control.Neq = int(value)

                            if key == "Np_per_side":
                                self.control.np_per_side = np.array(value, dtype=int)

                            # Saving interval
                            if key == "dump_step":
                                self.control.dump_step = int(value)

                            if key == "therm_dump_step":
                                self.control.therm_dump_step = int(value)

                            # Write the XYZ file, Yes/No
                            if key == "writexyz":
                                if value is False:
                                    self.control.writexyz = 0
                                if value is True:
                                    self.control.writexyz = 1

                            # verbose screen print out
                            if key == "verbose":
                                if value is False:
                                    self.control.verbose = 0
                                if value is True:
                                    self.control.verbose = 1

                            # Directory where to store Checkpoint files
                            if key == "simulations_dir":
                                self.control.simulations_dir = value

                            # Directory where to store Checkpoint files
                            if key == "job_dir":
                                self.control.job_dir = value

                            if key == "equilibration_dir":
                                self.control.equilibration_dir = value

                            if key == "rand_seed":
                                self.rand_seed = int(value)

                            # Filenames appendix
                            if key == "job_id":
                                self.control.job_id = value

        # Check for conflicts in case of magnetic field
        if self.Magnetic.on and self.Magnetic.elec_therm:
            self.integrator.mag_type = value
            self.integrator.type = 'Verlet'

        # Check for thermostat temperatures
        if not hasattr(self.thermostat, 'temperatures'):
            self.thermostat.temperatures = np.zeros(len(self.species))
            for i, sp in enumerate(self.species):
                self.thermostat.temperatures[i] = sp.temperature

    def create_directories(self, args):
        """
        Check for undefined control variables and create output directory and its subdirectories.

        Parameters
        ---------
        args: dict
            Input arguments.

        """
        # Check for directories

        if self.control.job_dir is None:
            if args["job_dir"] is None:
                self.control.job_dir = 'job_dir'
            else:
                self.control.job_dir = args["job_dir"]
        else:
            # Input option supersedes YAML file
            if not args["job_dir"] is None:
                self.control.job_dir = args["job_dir"]

        if self.control.job_id is None:
            if args["job_id"] is None and args["job_dir"] is None:
                self.control.job_id = "jobid"
            elif args["job_id"] is None and args["job_dir"] is not None:
                self.control.job_id = args["job_dir"]
            else:
                self.control.job_id = args["job_id"]
        else:
            # Input option supersedes YAML file
            if args["job_id"] is not None:
                self.control.job_id = args["job_id"]

        # Check if the directories exist
        if not os.path.exists(self.control.simulations_dir):
            os.mkdir(self.control.simulations_dir)

        self.control.job_dir = os.path.join(self.control.simulations_dir, self.control.job_dir)
        if not os.path.exists(self.control.job_dir):
            os.mkdir(self.control.job_dir)

        self.control.dump_dir = os.path.join(self.control.job_dir, self.control.dump_dir)
        if not os.path.exists(self.control.dump_dir):
            os.mkdir(self.control.dump_dir)

        self.control.therm_dir = os.path.join(self.control.job_dir, self.control.therm_dir)
        if not os.path.exists(self.control.therm_dir):
            os.mkdir(self.control.therm_dir)

        self.control.therm_dump_dir = os.path.join(self.control.therm_dir, "dumps")
        if not os.path.exists(self.control.therm_dump_dir):
            os.mkdir(self.control.therm_dump_dir)

        if self.control.log_file is None:
            self.control.log_file = os.path.join(self.control.job_dir, 'log.out')

    def assign_attributes(self):
        """ Assign the parsed parameters"""
        self.num_species = len(self.species)
        # Physical constants
        if self.control.units == "cgs":
            self.kB *= self.J2erg
            self.c0 *= 1e2  # cm/s
            if not (self.potential.type == "LJ"):
                # Coulomb to statCoulomb conversion factor. See https://en.wikipedia.org/wiki/Statcoulomb
                C2statC = 1.0e-01 * self.c0
                self.hbar = self.J2erg * self.hbar
                self.hbar2 = self.hbar ** 2
                self.qe *= C2statC
                self.me *= 1.0e3
                self.eps0 = 1.0
                self.fourpie0 = 1.0
                self.a0 *= 1e2

        # Check mass input
        for ic in range(self.num_species):
            if hasattr(self.species[ic], "atomic_weight"):
                # Choose between atomic mass constant or proton mass
                # u = const.physical_constants["atomic mass constant"][0]
                mp = const.physical_constants["proton mass"][0]

                if self.control.units == "cgs":
                    self.species[ic].mass = mp * 1e3 * self.species[ic].atomic_weight
                elif self.control.units == "mks":
                    self.species[ic].mass = mp * self.species[ic].atomic_weight

            if hasattr(self.species[ic], "mass_density"):
                Av = const.physical_constants["Avogadro constant"][0]
                self.species[ic].num_density = self.species[ic].mass_density * Av / self.species[ic].atomic_weight
                self.total_num_density += self.species[ic].num_density
        # Concentrations arrays and ions' total temperature
        self.Ti = 0.0
        for ic in range(self.num_species):
            self.species[ic].concentration = self.species[ic].num / self.total_num_ptcls
            self.Ti += self.species[ic].concentration * self.species[ic].temperature

        # Wigner-Seitz radius calculated from the total density
        self.aws = (3.0 / (4.0 * np.pi * self.total_num_density)) ** (1. / 3.)

        if not (self.potential.type == "LJ"):
            for ic in range(self.num_species):

                self.species[ic].charge = self.qe

                if hasattr(self.species[ic], "Z"):
                    self.species[ic].charge *= self.species[ic].Z

                if self.Magnetic.on:
                    if self.control.units == "cgs":
                        #  See https://en.wikipedia.org/wiki/Lorentz_force
                        self.species[ic].omega_c = self.species[ic].charge * self.Magnetic.BField / self.species[
                            ic].mass
                        self.species[ic].omega_c = self.species[ic].omega_c / self.c0
                    elif self.control.units == "mks":
                        self.species[ic].omega_c = self.species[ic].charge * self.Magnetic.BField / self.species[
                            ic].mass

                # Q^2 factor see eq.(2.10) in Ballenegger et al. J Chem Phys 128 034109 (2008)
                self.species[ic].QFactor = self.species[ic].num * self.species[ic].charge ** 2

                self.QFactor += self.species[ic].QFactor
                self.tot_net_charge += self.species[ic].charge * self.species[ic].num

        # Calculate electron number density from the charge neutrality condition in case of Yukawa or EGS potential
        if self.potential.type == "Yukawa" or self.potential.type == "EGS":
            for ic in range(self.num_species):
                if hasattr(self.species[ic], "Z"):
                    self.ne += self.species[ic].Z * self.species[ic].num_density

        # Simulation Box Parameters
        if len(self.control.np_per_side) != 0:
            msg = "Number of particles per dimension does not match total number of particles."
            assert int(np.prod(self.control.np_per_side)) == self.total_num_ptcls, msg

            self.Lx = self.aws * self.control.np_per_side[0] * (4.0 * np.pi / 3.0) ** (1.0 / 3.0)
            self.Ly = self.aws * self.control.np_per_side[1] * (4.0 * np.pi / 3.0) ** (1.0 / 3.0)
            self.Lz = self.aws * self.control.np_per_side[2] * (4.0 * np.pi / 3.0) ** (1.0 / 3.0)
        else:
            self.Lx = self.aws * (4.0 * np.pi * self.total_num_ptcls / 3.0) ** (1.0 / 3.0)
            self.Ly = self.aws * (4.0 * np.pi * self.total_num_ptcls / 3.0) ** (1.0 / 3.0)
            self.Lz = self.aws * (4.0 * np.pi * self.total_num_ptcls / 3.0) ** (1.0 / 3.0)

        self.Lv = np.array([self.Lx, self.Ly, self.Lz])  # box length vector

        # Dev Note: The following are useful for future geometries
        self.e1 = np.array([self.Lx, 0.0, 0.0])
        self.e2 = np.array([0.0, self.Ly, 0.0])
        self.e3 = np.array([0.0, 0.0, self.Lz])

        self.box_volume = abs(np.dot(np.cross(self.e1, self.e2), self.e3))

        self.dimensions = np.count_nonzero(self.Lv)  # no. of dimensions

        self.T_desired = self.Ti

        # boundary Conditions
        if self.BC.pbc_axes:
            self.BC.pbc_axes_indx = np.zeros(len(self.BC.pbc_axes))
            for (ij, bc) in enumerate(self.BC.pbc_axes):
                if bc == "x":
                    self.BC.pbc_axes_indx[ij] = 0
                elif bc == "y":
                    self.BC.pbc_axes_indx[ij] = 1
                elif bc == "z":
                    self.BC.pbc_axes_indx[ij] = 2

        if self.BC.mm_axes:
            print("\nOnly Periodic Boundary Conditions are supported. Bye!")
            sys.exit()
            self.BC.mm_axes_indx = np.zeros(len(self.BC.mm_axes), dtype=np.int)
            for (ij, bc) in enumerate(self.BC.mm_axes):
                if bc == "x":
                    self.BC.mm_axes_indx[ij] = 0
                elif bc == "y":
                    self.BC.mm_axes_indx[ij] = 1
                elif bc == "z":
                    self.BC.mm_axes_indx[ij] = 2

        if self.BC.open_axes:
            self.BC.open_axes_indx = np.zeros(len(self.BC.open_axes), dtype=np.int)
            for (ij, bc) in enumerate(self.BC.open_axes):
                if bc == "x":
                    self.BC.open_axes_indx[ij] = 0
                elif bc == "y":
                    self.BC.open_axes_indx[ij] = 1
                elif bc == "z":
                    self.BC.open_axes_indx[ij] = 2
        return

    def from_input_dict(self, args):
        """

        Parameters
        ----------
        args

        Returns
        -------

        """

