"""
Module for calculating physical quantities from Sarkas checkpoints.
"""
import os
from tqdm import tqdm
import numpy as np
from numba import njit
import pandas as pd
from matplotlib.gridspec import GridSpec
import matplotlib.pyplot as plt

#
# plt.style.use(
#     os.path.join(os.path.join(os.getcwd(), 'src'), 'PUBstyle'))

UNITS = [
    {"Energy": 'J',
     "Time": 's',
     "Length": 'm',
     "Charge": 'C',
     "Temperature": 'K',
     "ElectronVolt": 'eV',
     "Mass": 'kg',
     "Magnetic Field": 'T',
     "Current": "A",
     "Power": "erg/s",
     "Pressure": "Pa",
     "none": ""},
    {"Energy": 'erg',
     "Time": 's',
     "Length": 'cm',
     "Charge": 'esu',
     "Temperature": 'K',
     "ElectronVolt": 'eV',
     "Mass": 'g',
     "Magnetic Field": 'G',
     "Current": "esu/s",
     "Power": "erg/s",
     "Pressure": "Ba",
     "none": ""}
]

PREFIXES = {
    "Y": 1e24,
    "Z": 1e21,
    "E": 1e18,
    "P": 1e15,
    "T": 1e12,
    "G": 1e9,
    "M": 1e6,
    "k": 1e3,
    "": 1e0,
    "c": 1.0e-2,
    "m": 1.0e-3,
    r"$\mu$": 1.0e-6,
    "n": 1.0e-9,
    "p": 1.0e-12,
    "f": 1.0e-15,
    "a": 1.0e-18,
    "z": 1.0e-21,
    "y": 1.0e-24
}


class CurrentCorrelationFunctions:
    """
    Current Correlation Functions: :math:`L(k,\\omega)` and :math:`T(k,\\omega)`.

    Parameters
    ----------
    params : object
        Simulation's parameters

    Attributes
    ----------
    a_ws : float
        Wigner-Seitz radius.

    wp : float
        Total plasma frequency.

    dump_step : int
        Dump step frequency.

    dataframe_l : Pandas dataframe
        Dataframe of the longitudinal velocity correlation functions.

    dataframe_t : Pandas dataframe
        Dataframe of the transverse velocity correlation functions.

    l_filename_csv: str
        Name of file for the longitudinal velocities fluctuation correlation function.

    t_filename_csv: str
        Name of file for the transverse velocities fluctuation correlation function.

    fldr : str
        Job's directory.

    no_dumps : int
        Number of dumps.

    no_species : int
        Number of species.

    species_np: array
        Array of integers with the number of particles for each species.

    dt : float
        Timestep's value normalized by the total plasma frequency.

    species_names : list
        Names of particle species.

    species_wp : array
        Plasma frequency of each species.

    tot_no_ptcls : int
        Total number of particles.

    ptcls_fldr : str
        Directory of Sarkas dumps.

    k_fldr : str
        Directory of :math:`k`-space fluctuations.

    vkt_file : str
        Name of file containing velocity fluctuations functions of each species.

    k_file : str
        Name of file containing ``k_list``, ``k_counts``, ``ka_values``.

    k_list : list
        List of all possible :math:`k` vectors with their corresponding magnitudes and indexes.

    k_counts : array
        Number of occurrences of each :math:`k` magnitude.

    ka_values : array
        Magnitude of each allowed :math:`ka` vector.

    no_ka_values: int
        Length of ``ka_values`` array.

    box_lengths : array
        Length of each box side.
    """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.dataframe_l = None
        self.dataframe_t = None
        self.k_counts = None
        self.ka_values = None
        self.k_list = None
        self.fldr = params.control.checkpoint_dir
        self.ptcls_fldr = params.control.dump_dir
        self.k_fldr = os.path.join(self.fldr, "k_space_data")
        self.k_file = os.path.join(self.k_fldr, "k_arrays.npz")
        self.vkt_file = os.path.join(self.k_fldr, "vkt.npz")
        self.job_id = params.control.fname_app
        self.l_filename_csv = os.path.join(self.fldr,
                                           "LongitudinalVelocityCorrelationFunction_" + self.job_id + '.csv')
        self.t_filename_csv = os.path.join(self.fldr,
                                           "TransverseVelocityCorrelationFunction_" + self.job_id + '.csv')

        self.box_lengths = np.array([params.Lx, params.Ly, params.Lz])
        self.dump_step = params.control.dump_step
        self.no_dumps = len(os.listdir(params.control.dump_dir))
        self.no_species = len(params.species)
        self.tot_no_ptcls = params.total_num_ptcls

        self.species_np = np.zeros(self.no_species, dtype=int)
        self.species_names = []
        self.species_wp = np.zeros(self.no_species)
        for i, sp in enumerate(params.species):
            self.species_wp[i] = sp.wp
            self.species_np[i] = int(sp.num)
            self.species_names.append(sp.name)

        self.dt = params.control.dt
        self.a_ws = params.aws
        self.wp = params.wp

        # Create the lists of k vectors
        if len(params.PostProcessing.dsf_no_ka_values) == 0:
            self.no_ka = np.array([params.PostProcessing.dsf_no_ka_values,
                                   params.PostProcessing.dsf_no_ka_values,
                                   params.PostProcessing.dsf_no_ka_values], dtype=int)
        else:
            self.no_ka = params.PostProcessing.dsf_no_ka_values  # number of ka values

    def parse(self):
        """
        Grab the pandas dataframe from the saved csv file. If file does not exist call ``compute``.
        """
        try:
            self.dataframe_l = pd.read_csv(self.l_filename_csv, index_col=False)
            self.dataframe_t = pd.read_csv(self.t_filename_csv, index_col=False)
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]
        except FileNotFoundError:
            print("\nFiles not found!")
            print("\nComputing CCF now ...")
            self.compute()

    def compute(self):
        """
        Calculate the velocity fluctuations correlation functions.
        """
        data = {"Frequencies": 2.0 * np.pi * np.fft.fftfreq(self.no_dumps, self.dt * self.dump_step)}
        data2 = {"Frequencies": 2.0 * np.pi * np.fft.fftfreq(self.no_dumps, self.dt * self.dump_step)}
        self.dataframe_l = pd.DataFrame(data)
        self.dataframe_t = pd.DataFrame(data2)
        # Parse vkt otherwise calculate them
        try:
            data = np.load(self.vkt_file)
            vkt = data["longitudinal"]
            vkt_i = data["transverse_i"]
            vkt_j = data["transverse_j"]
            vkt_k = data["transverse_k"]
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]
            self.no_ka_values = len(self.ka_values)

        except FileNotFoundError:
            self.k_list, self.k_counts, k_unique = kspace_setup(self.no_ka, self.box_lengths)
            self.ka_values = 2.0 * np.pi * k_unique * self.a_ws
            self.no_ka_values = len(self.ka_values)

            if not (os.path.exists(self.k_fldr)):
                os.mkdir(self.k_fldr)

            np.savez(self.k_file,
                     k_list=self.k_list,
                     k_counts=self.k_counts,
                     ka_values=self.ka_values)

            vkt, vkt_i, vkt_j, vkt_k = calc_vkt(self.ptcls_fldr, self.no_dumps, self.dump_step, self.species_np,
                                                self.k_list)
            np.savez(self.vkt_file,
                     longitudinal=vkt,
                     transverse_i=vkt_i,
                     transverse_j=vkt_j,
                     transverse_k=vkt_k)

        # Calculate Lkw
        Lkw = calc_Skw(vkt, self.k_list, self.k_counts, self.species_np, self.no_dumps, self.dt, self.dump_step)
        Tkw_i = calc_Skw(vkt_i, self.k_list, self.k_counts, self.species_np, self.no_dumps, self.dt, self.dump_step)
        Tkw_j = calc_Skw(vkt_j, self.k_list, self.k_counts, self.species_np, self.no_dumps, self.dt, self.dump_step)
        Tkw_k = calc_Skw(vkt_k, self.k_list, self.k_counts, self.species_np, self.no_dumps, self.dt, self.dump_step)
        Tkw = (Tkw_i + Tkw_j + Tkw_k) / 3.0
        print("Saving L(k,w) and T(k,w)")
        sp_indx = 0
        for sp_i in range(self.no_species):
            for sp_j in range(sp_i, self.no_species):
                for ik in range(len(self.k_counts)):
                    if ik == 0:
                        column = "{}-{} CCF ka_min".format(self.species_names[sp_i], self.species_names[sp_j])
                    else:
                        column = "{}-{} CCF {} ka_min".format(self.species_names[sp_i],
                                                              self.species_names[sp_j], ik + 1)

                    self.dataframe_l[column] = Lkw[sp_indx, ik, :]
                    self.dataframe_t[column] = Tkw[sp_indx, ik, :]
                sp_indx += 1

        self.dataframe_l.to_csv(self.l_filename_csv, index=False, encoding='utf-8')
        self.dataframe_t.to_csv(self.t_filename_csv, index=False, encoding='utf-8')

        return

    def plot(self, longitudinal=True, show=False, dispersion=False):
        """
        Plot velocity fluctuations correlation functions and save the figure.

        Parameters
        ----------
        longitudinal : bool
            Flag for plotting longitudinal or transverse correlation function. Default=True.

        show: bool
            Flag for prompting the plots to screen. Default=False

        dispersion : bool
            Flag for plotting the collective mode dispersion. Default=False

        """
        try:
            if longitudinal:
                self.dataframe = pd.read_csv(self.l_filename_csv, index_col=False)
                lbl = "L"
            else:
                self.dataframe = pd.read_csv(self.t_filename_csv, index_col=False)
                lbl = "T"
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]
            self.no_ka_values = len(self.ka_values)
        except FileNotFoundError:
            print("Computing L(k,w), T(k,w)")
            self.compute()

        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        if self.no_species > 1:
            for sp_i in range(self.no_species):
                for sp_j in range(sp_i, self.no_species):
                    column = "{}-{} CCF ka_min".format(self.species_names[sp_i], self.species_names[sp_j])
                    ax.plot(np.fft.fftshift(self.dataframe["Frequencies"]) / self.species_wp[0],
                            np.fft.fftshift(self.dataframe[column]),
                            label=r'$' + lbl + '_{' + self.species_names[sp_i] + self.species_names[sp_j] + '}(k,'
                                                                                                            '\omega)$')
        else:
            column = "{}-{} CCF ka_min".format(self.species_names[0], self.species_names[0])
            ax.plot(np.fft.fftshift(self.dataframe["Frequencies"]) / self.species_wp[0],
                    np.fft.fftshift(self.dataframe[column]),
                    label=r'$ka = {:1.4f}$'.format(self.ka_values[0]))
            for i in range(1, 5):
                column = "{}-{} CCF {} ka_min".format(self.species_names[0], self.species_names[0], i + 1)
                ax.plot(np.fft.fftshift(self.dataframe["Frequencies"]) / self.wp,
                        np.fft.fftshift(self.dataframe[column]),
                        label=r'$ka = {:1.4f}$'.format(self.ka_values[i]))

        ax.grid(True, alpha=0.3)
        ax.legend(loc='best', ncol=3)
        ax.set_yscale('log')
        ax.set_xlim(0, 3)
        if longitudinal:
            ax.set_ylabel(r'$L(k,\omega)$')
            fig_name = os.path.join(self.fldr, 'Lkw_' + self.job_id + '.png')
        else:
            ax.set_ylabel(r'$T(k,\omega)$')
            fig_name = os.path.join(self.fldr, 'Tkw_' + self.job_id + '.png')

        ax.set_xlabel(r'$\omega/\omega_p$')
        fig.tight_layout()
        fig.savefig(fig_name)
        if show:
            fig.show()

        if dispersion:
            w_array = np.array(self.dataframe["Frequencies"]) / self.wp
            neg_indx = np.where(w_array < 0.0)[0][0]
            Skw = np.array(self.dataframe.iloc[:, 1:self.no_ka_values + 1])
            ka_vals, w = np.meshgrid(self.ka_values, w_array[:neg_indx])
            fig = plt.figure(figsize=(10, 7))
            plt.pcolor(ka_vals, w, Skw[neg_indx:, :], vmin=Skw[:, 1].min(), vmax=Skw[:, 1].max())
            cbar = plt.colorbar()
            cbar.set_ticks([])
            cbar.ax.tick_params(labelsize=14)
            plt.xlabel(r'$ka$')
            plt.ylabel(r'$\omega/\omega_p$')
            plt.ylim(0, 2)
            plt.tick_params(axis='both', which='major')
            fig.tight_layout()
            if longitudinal:
                fig.savefig(os.path.join(self.fldr, 'Lkw_Dispersion_' + self.job_id + '.png'))
            else:
                fig.savefig(os.path.join(self.fldr, 'Tkw_Dispersion_' + self.job_id + '.png'))
            if show:
                fig.show()


class DynamicStructureFactor:
    """
    Dynamic Structure factor.

    Parameters
    ----------
    params : object
        Simulation's parameters

    Attributes
    ----------
        a_ws : float
            Wigner-Seitz radius.

        wp : float
            Total plasma frequency.

        dump_step : int
            Dump step frequency.

        dataframe : Pandas dataframe
            Dataframe of the dynamic structure functions.

        filename_csv: str
            Filename in which to store the Dynamic structure functions.

        fldr : str
            Job's directory.

        no_dumps : int
            Number of dumps.

        no_species : int
            Number of species.

        species_np: array
            Array of integers with the number of particles for each species.

        dt : float
            Timestep's value normalized by the total plasma frequency.

        species_names : list
            Names of particle species.

        species_wp : array
            Plasma frequency of each species.

        tot_no_ptcls : int
            Total number of particles.

        ptcls_fldr : str
            Directory of Sarkas dumps.

        k_fldr : str
            Directory of :math:`k`-space fluctuations.

        nkt_file : str
            Name of file containing density fluctuations functions of each species.

        k_file : str
            Name of file containing ``k_list``, ``k_counts``, ``ka_values``.

        k_list : list
            List of all possible :math:`k` vectors with their corresponding magnitudes and indexes.

        k_counts : array
            Number of occurrences of each :math:`k` magnitude.

        ka_values : array
            Magnitude of each allowed :math:`ka` vector.

        no_ka_values: int
            Length of ``ka_values`` array.

        box_lengths : array
            Length of each box side.
        """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.fldr = params.control.checkpoint_dir
        self.ptcls_fldr = params.control.dump_dir
        self.k_fldr = os.path.join(self.fldr, "k_space_data")
        self.k_file = os.path.join(self.k_fldr, "k_arrays.npz")
        self.nkt_file = os.path.join(self.k_fldr, "nkt.npy")
        self.job_id = params.control.fname_app
        self.filename_csv = os.path.join(self.fldr, "DynamicStructureFactor_" + self.job_id + '.csv')

        self.box_lengths = np.array([params.Lx, params.Ly, params.Lz])
        self.dump_step = params.control.dump_step
        self.no_dumps = len(os.listdir(params.control.dump_dir))
        self.no_species = len(params.species)
        self.tot_no_ptcls = params.total_num_ptcls

        self.species_np = np.zeros(self.no_species, dtype=int)
        self.species_names = []
        self.species_wp = np.zeros(self.no_species)
        for i, sp in enumerate(params.species):
            self.species_wp[i] = sp.wp
            self.species_np[i] = int(sp.num)
            self.species_names.append(sp.name)

        self.Nsteps = params.control.Nsteps
        self.dt = params.control.dt
        self.no_Skw = int(self.no_species * (self.no_species + 1) / 2)
        self.a_ws = params.aws
        self.wp = params.wp

        # Create the lists of k vectors
        if len(params.PostProcessing.dsf_no_ka_values) == 0:
            self.no_ka = np.array([params.PostProcessing.dsf_no_ka_values,
                                   params.PostProcessing.dsf_no_ka_values,
                                   params.PostProcessing.dsf_no_ka_values], dtype=int)
        else:
            self.no_ka = params.PostProcessing.dsf_no_ka_values  # number of ka values

    def parse(self):
        """
        Grab the pandas dataframe from the saved csv file. If file does not exist call ``compute``.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]

        except FileNotFoundError:
            print("\nFile {} not found!".format(self.filename_csv))
            print("\nComputing DSF now...")
            self.compute()
        return

    def compute(self):
        """
        Compute :math:`S_{ij} (k,\\omega)` and the array of :math:`\\omega` values.
        ``self.Skw``. Shape = (``no_ws``, ``no_Sij``)
        """

        data = {"Frequencies": 2.0 * np.pi * np.fft.fftfreq(self.no_dumps, self.dt * self.dump_step)}
        self.dataframe = pd.DataFrame(data)

        # Parse nkt otherwise calculate it
        try:
            nkt = np.load(self.nkt_file)
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]
            self.no_ka_values = len(self.ka_values)
            print("Loaded")
            print(nkt.shape)
        except FileNotFoundError:
            self.k_list, self.k_counts, k_unique = kspace_setup(self.no_ka, self.box_lengths)
            self.ka_values = 2.0 * np.pi * k_unique * self.a_ws
            self.no_ka_values = len(self.ka_values)

            if not (os.path.exists(self.k_fldr)):
                os.mkdir(self.k_fldr)

            np.savez(self.k_file,
                     k_list=self.k_list,
                     k_counts=self.k_counts,
                     ka_values=self.ka_values)

            nkt = calc_nkt(self.ptcls_fldr, self.no_dumps, self.dump_step, self.species_np, self.k_list)
            np.save(self.nkt_file, nkt)

        # Calculate Skw
        Skw = calc_Skw(nkt, self.k_list, self.k_counts, self.species_np, self.no_dumps, self.dt, self.dump_step)
        print("Saving S(k,w)")
        sp_indx = 0
        for sp_i in range(self.no_species):
            for sp_j in range(sp_i, self.no_species):
                for ik in range(len(self.k_counts)):
                    if ik == 0:
                        column = "{}-{} DSF ka_min".format(self.species_names[sp_i], self.species_names[sp_j])
                    else:
                        column = "{}-{} DSF {} ka_min".format(self.species_names[sp_i],
                                                              self.species_names[sp_j], ik + 1)
                    self.dataframe[column] = Skw[sp_indx, ik, :]
                sp_indx += 1

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')

        return

    def plot(self, show=False, dispersion=False):
        """
        Plot :math:`S(k,\\omega)` and save the figure.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]
            self.no_ka_values = len(self.ka_values)
        except FileNotFoundError:
            print("Computing S(k,w)")
            self.compute()

        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        if self.no_species > 1:
            for sp_i in range(self.no_species):
                for sp_j in range(sp_i, self.no_species):
                    column = "{}-{} DSF ka_min".format(self.species_names[sp_i], self.species_names[sp_j])
                    ax.plot(np.fft.fftshift(self.dataframe["Frequencies"]) / self.species_wp[0],
                            np.fft.fftshift(self.dataframe[column]),
                            label=r'$S_{' + self.species_names[sp_i] + self.species_names[sp_j] + '}(k,\omega)$')
        else:
            column = "{}-{} DSF ka_min".format(self.species_names[0], self.species_names[0])
            ax.plot(np.fft.fftshift(self.dataframe["Frequencies"]) / self.species_wp[0],
                    np.fft.fftshift(self.dataframe[column]),
                    label=r'$ka = {:1.4f}$'.format(self.ka_values[0]))
            for i in range(1, 5):
                column = "{}-{} DSF {} ka_min".format(self.species_names[0], self.species_names[0], i + 1)
                ax.plot(np.fft.fftshift(self.dataframe["Frequencies"]) / self.wp,
                        np.fft.fftshift(self.dataframe[column]),
                        label=r'$ka = {:1.4f}$'.format(self.ka_values[i]))

        ax.grid(True, alpha=0.3)
        ax.legend(loc='best', ncol=3)
        ax.set_yscale('log')
        ax.set_xlim(0, 3)
        ax.set_ylabel(r'$S(k,\omega)$')
        ax.set_xlabel(r'$\omega/\omega_p$')
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, 'Skw_' + self.job_id + '.png'))
        if show:
            fig.show()

        if dispersion:
            w_array = np.array(self.dataframe["Frequencies"]) / self.wp
            neg_indx = np.where(w_array < 0.0)[0][0]
            Skw = np.array(self.dataframe.iloc[:, 1:self.no_ka_values + 1])
            ka_vals, w = np.meshgrid(self.ka_values, w_array[: neg_indx])
            fig = plt.figure(figsize=(10, 7))
            plt.pcolor(ka_vals, w, Skw[: neg_indx, :], vmin=Skw[:, 1].min(), vmax=Skw[:, 1].max())
            cbar = plt.colorbar()
            cbar.set_ticks([])
            cbar.ax.tick_params(labelsize=14)
            plt.xlabel(r'$ka$')
            plt.ylabel(r'$\omega/\omega_p$')
            plt.ylim(0, 2)
            plt.tick_params(axis='both', which='major')
            plt.title("$S(k, \omega)$")
            fig.tight_layout()
            fig.savefig(os.path.join(self.fldr, 'Skw_Dispersion_' + self.job_id + '.png'))
            if show:
                fig.show()


class ElectricCurrent:
    """
    Electric Current Auto-correlation function.

    Parameters
    ----------
    params : object
        Simulation's parameters

    Attributes
    ----------
    a_ws : float
        Wigner-Seitz radius.

    wp : float
        Total plasma frequency.

    dump_step : int
        Dump step frequency.

    dt : float
        Timestep magnitude.

    filename_csv: str
        Name of output files.

    fldr : str
        Folder containing dumps.

    no_dumps : int
        Number of dumps.

    no_species : int
        Number of species.

    species_np: array
        Array of integers with the number of particles for each species.

    species_charge: array
        Array of with the charge of each species.

    species_names : list
        Names of particle species.

    tot_no_ptcls : int
        Total number of particles.

    """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: object
            Simulation's parameters.
        """
        self.dataframe = None
        self.verbose = params.control.verbose
        self.fldr = params.control.checkpoint_dir
        self.job_id = params.control.fname_app
        self.units = params.control.units
        self.dump_dir = params.control.dump_dir
        self.filename_csv = os.path.join(self.fldr, "ElectricCurrent_" + self.job_id + '.csv')
        self.dump_step = params.control.dump_step
        self.no_dumps = len(os.listdir(params.control.dump_dir))
        self.no_species = len(params.species)
        self.species_np = np.zeros(self.no_species, dtype=int)
        self.species_names = []
        self.dt = params.control.dt  # No of dump to skip
        self.species_charge = np.zeros(self.no_species)
        for i, sp in enumerate(params.species):
            self.species_np[i] = int(sp.num)
            self.species_charge[i] = sp.charge
            self.species_names.append(sp.name)

        self.tot_no_ptcls = params.total_num_ptcls
        self.wp = params.wp
        self.a_ws = params.aws
        self.dt = params.control.dt

    def parse(self):
        """
        Grab the pandas dataframe from the saved csv file. If file does not exist call ``compute``.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            print("\nFile {} not found!".format(self.filename_csv))
            print("\nComputing Electric Current now ...")
            self.compute()

    def compute(self):
        """
        Compute the electric current and the corresponding auto-correlation functions.
        """

        # Parse the particles from the dump files
        vel = np.zeros((self.no_dumps, 3, self.tot_no_ptcls))
        #
        print("Parsing particles' velocities.")
        time = np.zeros(self.no_dumps)
        for it in tqdm(range(self.no_dumps), disable=(not self.verbose)):
            dump = int(it * self.dump_step)
            time[it] = dump * self.dt
            datap = load_from_restart(self.dump_dir, dump)
            vel[it, 0, :] = datap["vel"][:, 0]
            vel[it, 1, :] = datap["vel"][:, 1]
            vel[it, 2, :] = datap["vel"][:, 2]
        #
        print("Calculating Electric current quantities.")
        species_current, total_current = calc_elec_current(vel, self.species_charge, self.species_np)
        data_dic = {"Time": time}
        self.dataframe = pd.DataFrame(data_dic)

        self.dataframe["Total Current X"] = total_current[0, :]
        self.dataframe["Total Current Y"] = total_current[1, :]
        self.dataframe["Total Current Z"] = total_current[2, :]

        cur_acf_xx = autocorrelationfunction_1D(total_current[0, :])
        cur_acf_yy = autocorrelationfunction_1D(total_current[1, :])
        cur_acf_zz = autocorrelationfunction_1D(total_current[2, :])

        tot_cur_acf = autocorrelationfunction(total_current)
        # Normalize and save
        self.dataframe["X Current ACF"] = cur_acf_xx / cur_acf_xx[0]
        self.dataframe["Y Current ACF"] = cur_acf_yy / cur_acf_yy[0]
        self.dataframe["Z Current ACF"] = cur_acf_zz / cur_acf_zz[0]
        self.dataframe["Total Current ACF"] = tot_cur_acf / tot_cur_acf[0]
        for sp in range(self.no_species):
            tot_acf = autocorrelationfunction(species_current[sp, :, :])
            acf_xx = autocorrelationfunction_1D(species_current[sp, 0, :])
            acf_yy = autocorrelationfunction_1D(species_current[sp, 1, :])
            acf_zz = autocorrelationfunction_1D(species_current[sp, 2, :])

            self.dataframe["{} Total Current".format(self.species_names[sp])] = np.sqrt(
                species_current[sp, 0, :] ** 2 + species_current[sp, 1, :] ** 2 + species_current[sp, 2, :] ** 2)
            self.dataframe["{} X Current".format(self.species_names[sp])] = species_current[sp, 0, :]
            self.dataframe["{} Y Current".format(self.species_names[sp])] = species_current[sp, 1, :]
            self.dataframe["{} Z Current".format(self.species_names[sp])] = species_current[sp, 2, :]

            self.dataframe["{} Total Current ACF".format(self.species_names[sp])] = tot_acf / tot_acf[0]
            self.dataframe["{} X Current ACF".format(self.species_names[sp])] = acf_xx / acf_xx[0]
            self.dataframe["{} Y Current ACF".format(self.species_names[sp])] = acf_yy / acf_yy[0]
            self.dataframe["{} Z Current ACF".format(self.species_names[sp])] = acf_zz / acf_zz[0]

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')
        return

    def plot(self, show=False):
        """
        Plot the electric current autocorrelation function and save the figure.

        Parameters
        ----------
        show: bool
            Prompt the plot to screen.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            self.compute()

        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        xmul, ymul, xprefix, yprefix, xlbl, ylbl = plot_labels(self.dataframe["Time"],
                                                               self.dataframe["Total Current ACF"], "Time", "none",
                                                               self.units)
        ax.plot(xmul * self.dataframe["Time"], self.dataframe["Total Current ACF"], '--o', label=r'$J_{tot} (t)$')

        ax.legend(loc='upper right')
        ax.set_ylabel(r'$J(t)$')
        ax.set_xlabel('Time' + xlbl)
        ax.set_xscale('log')
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, 'TotalCurrentACF_' + self.job_id + '.png'))
        if show:
            fig.show()


class HermiteCoefficients:
    """
    Hermite coefficients of the Hermite expansion.

    Parameters
    ----------
    params : object
        Simulation's parameters

    Attributes
    ----------
    dump_dir: str
        Directory containing simulation's dumps.

    dump_step : int
        Dump step frequency.

    filename_csv: str
        Filename in which to store the Pandas dataframe.

    fldr: str
        Job's directory.

    fname_app: str
        Appendix of file names.

    hermite_order: int
        Order of the Hermite expansion.

    no_bins: int
        Number of bins used to calculate the velocity distribution.

    no_dumps: int
        Number of simulation's dumps to compute.

    plots_dir: str
        Directory in which to store Hermite coefficients plots.

    a_ws : float
        Wigner-Seitz radius.

    wp : float
        Total plasma frequency.

    kB : float
        Boltzmann constant.

    dt : float
        Timestep magnitude.

    no_species : int
        Number of species.

    species_np: array
        Array of integers with the number of particles for each species.

    species_names : list
        Names of particle species.

    tot_no_ptcls : int
        Total number of particles.

    species_plots_dirs : list, str
        Directory for each species where to save Hermite coefficients plots.

    units: str
        System of units used in the simulation. mks or cgs.

    """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.dataframe = None
        self.species_plots_dirs = None
        if not hasattr(params.PostProcessing, 'hermite_nbins'):
            self.no_bins = int(0.05 * params.total_num_ptcls)
        else:
            self.no_bins = params.PostProcessing.hermite_nbins  # number of ka values

        if not hasattr(params.PostProcessing, 'hermite_order'):
            self.hermite_order = 7
        else:
            self.hermite_order = params.PostProcessing.hermite_order
        self.dump_dir = params.control.dump_dir
        self.no_dumps = len(os.listdir(params.control.dump_dir))
        #
        self.fldr = os.path.join(params.control.checkpoint_dir, 'HermiteExp_data')
        if not os.path.exists(self.fldr):
            os.mkdir(self.fldr)
        self.plots_dir = os.path.join(self.fldr, 'Hermite_Plots')
        self.job_id = params.control.fname_app
        self.filename_csv = os.path.join(self.fldr, "HermiteCoefficients_" + self.job_id + '.csv')
        self.dump_step = params.control.dump_step
        self.units = params.control.units
        self.no_species = len(params.species)
        self.tot_no_ptcls = params.total_num_ptcls
        self.no_dim = params.dimensions
        self.no_steps = params.control.Nsteps
        self.a_ws = params.aws
        self.wp = params.wp
        self.kB = params.kB
        self.species_np = np.zeros(self.no_species)  # Number of particles of each species
        self.species_masses = np.zeros(self.no_species)  # Number of particles of each species
        self.species_names = []
        self.dt = params.control.dt
        self.species_temperatures = params.thermostat.temperatures

        for i, sp in enumerate(params.species):
            self.species_np[i] = int(sp.num)
            self.species_names.append(sp.name)
            self.species_masses[i] = sp.mass

    def compute(self):
        """
        Calculate Hermite coefficients and save the pandas dataframe.
        """
        vscale = 1.0 / (self.a_ws * self.wp)
        vel = np.zeros((self.no_dim, self.tot_no_ptcls))

        xcoeff = np.zeros((self.no_species, self.no_dumps, self.hermite_order + 1))
        ycoeff = np.zeros((self.no_species, self.no_dumps, self.hermite_order + 1))
        zcoeff = np.zeros((self.no_species, self.no_dumps, self.hermite_order + 1))

        time = np.zeros(self.no_dumps)
        print("Computing Hermite Coefficients ...")
        for it in range(self.no_dumps):
            time[it] = it * self.dt * self.dump_step
            dump = int(it * self.dump_step)
            datap = load_from_restart(self.dump_dir, dump)
            vel[0, :] = datap["vel"][:, 0]
            vel[1, :] = datap["vel"][:, 1]
            vel[2, :] = datap["vel"][:, 2]

            sp_start = 0
            for sp in range(self.no_species):
                sp_end = int(sp_start + self.species_np[sp])
                x_hist, xbins = np.histogram(vel[0, sp_start:sp_end] * vscale, bins=self.no_bins, density=True)
                y_hist, ybins = np.histogram(vel[1, sp_start:sp_end] * vscale, bins=self.no_bins, density=True)
                z_hist, zbins = np.histogram(vel[2, sp_start:sp_end] * vscale, bins=self.no_bins, density=True)

                # Center the bins
                vx = 0.5 * (xbins[:-1] + xbins[1:])
                vy = 0.5 * (ybins[:-1] + ybins[1:])
                vz = 0.5 * (zbins[:-1] + zbins[1:])

                xcoeff[sp, it, :] = calculate_herm_coeff(vx, x_hist, self.hermite_order)
                ycoeff[sp, it, :] = calculate_herm_coeff(vy, y_hist, self.hermite_order)
                zcoeff[sp, it, :] = calculate_herm_coeff(vz, z_hist, self.hermite_order)

                sp_start = sp_end

        data = {"Time": time}
        self.dataframe = pd.DataFrame(data)

        for sp in range(self.no_species):
            for hi in range(self.hermite_order + 1):
                self.dataframe["{} Hermite x Coeff a{}".format(self.species_names[sp], hi)] = xcoeff[sp, :, hi]
                self.dataframe["{} Hermite y Coeff a{}".format(self.species_names[sp], hi)] = ycoeff[sp, :, hi]
                self.dataframe["{} Hermite z Coeff a{}".format(self.species_names[sp], hi)] = zcoeff[sp, :, hi]

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')

    def parse(self):
        """
        Grab the pandas dataframe from the saved csv file. If file does not exist call ``compute``.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            print("\nFile {} not found!".format(self.filename_csv))
            print("\nComputing Hermite Coefficients now ...")
            self.compute()

    def plot(self, show=False):
        """
        Plot the Hermite coefficients and save the figure
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            self.compute()

        if not os.path.exists(self.plots_dir):
            os.mkdir(self.plots_dir)

        if self.no_species > 1:
            self.species_plots_dirs = []
            for i, name in enumerate(self.species_names):
                new_dir = os.path.join(self.plots_dir, "{}".format(name))
                self.species_plots_dirs.append(new_dir)
                if not os.path.exists(new_dir):
                    os.mkdir(os.path.join(self.plots_dir, "{}".format(name)))
        else:
            self.species_plots_dirs = [self.plots_dir]

        for sp, name in enumerate(self.species_names):
            print("Species: {}".format(name))
            fig, ax = plt.subplots(1, 2, sharex=True, constrained_layout=True, figsize=(16, 9))
            for indx in range(self.hermite_order):
                xcolumn = "{} Hermite x Coeff a{}".format(name, indx)
                ycolumn = "{} Hermite y Coeff a{}".format(name, indx)
                zcolumn = "{} Hermite z Coeff a{}".format(name, indx)
                xmul, ymul, xprefix, yprefix, xlbl, ylbl = plot_labels(self.dataframe["Time"], np.array([1.0]),
                                                                       'Time', 'none', self.units)
                ia = int(indx % 2)
                ax[ia].plot(self.dataframe["Time"] * xmul, self.dataframe[xcolumn] + ia * (indx - 1),
                            ls='-', label=r"$a_{" + str(indx) + " , x}$")
                ax[ia].plot(self.dataframe["Time"] * xmul, self.dataframe[ycolumn] + ia * (indx - 1),
                            ls='--', label=r"$a_{" + str(indx) + " , y}$")
                ax[ia].plot(self.dataframe["Time"] * xmul, self.dataframe[zcolumn] + ia * (indx - 1),
                            ls='-.', label=r"$a_{" + str(indx) + " , z}$")

            ax[0].set_title(r'Even Coefficients')
            ax[1].set_title(r'Odd Coefficients')

            ax[0].set_xlabel(r'$t$' + xlbl)
            ax[1].set_xlabel(r'$t$' + xlbl)

            sigma = np.sqrt(self.kB * self.species_temperatures[sp] / self.species_masses[sp]) / (self.a_ws * self.wp)

            for i in range(0, self.hermite_order, 2):
                coeff = np.zeros(i + 1)
                coeff[-1] = 1.0
                print("Equilibrium a{} = {:1.2f} ".format(i, np.polynomial.hermite_e.hermeval(sigma, coeff)))

            # t_end = self.dataframe["Time"].iloc[-1] * xmul/2
            # ax[0].text(t_end, 1.1, r"$a_{0,\rm{eq}} = 1 $", transform=ax[0].transData)
            # # ax[0].axhline(1, ls=':', c='k', label=r"$a_{0,\rm{eq}}$")
            #
            # ax[0].text(t_end, a2_eq * 0.97, r"$a_{2,\rm{eq}} = " + "{:1.2f}".format(a2_eq) +"$",
            #            transform=ax[0].transData)
            #
            # if self.hermite_order > 3:
            #     ax[0].text(t_end, a4_eq * 1.1, r"$a_{4,\rm{eq}} = " + "{:1.2f}".format(a4_eq) + "$",
            #                transform=ax[0].transData)
            #
            # if self.hermite_order > 5:
            #     ax[0].text(t_end, a6_eq * .98, r"$a_{6,\rm{eq}} = " + "{:1.2f}".format(a6_eq) + "$",
            #                transform=ax[0].transData)

            ax[0].legend(loc='best', ncol=int(self.hermite_order / 2 + self.hermite_order % 2))
            ax[1].legend(loc='best', ncol=int(self.hermite_order / 2))
            yt = np.arange(0, self.hermite_order + self.hermite_order % 2, 2)
            ax[1].set_yticks(yt)
            ax[1].set_yticklabels(np.zeros(len(yt)))
            fig.suptitle("Hermite Coefficients of {}".format(name))
            plot_name = os.path.join(self.species_plots_dirs[sp], '{}_HermCoeffPlot_'.format(name)
                                     + self.job_id + '.png')
            fig.savefig(plot_name)
            if show:
                fig.show()


class RadialDistributionFunction:
    """
    Radial Distribution Function.

    Parameters
    ----------
    params : object
        Simulation's parameters

    Attributes
    ----------
    a_ws : float
        Wigner-Seitz radius.

    box_lengths : array
        Length of each side of the box.

    box_volume : float
        Volume of simulation's box.

    dataframe : Pandas dataframe
        It contains the radial distribution functions.

    dump_step : int
        Dump step frequency.

    filename_csv: str
        Name of csv file containing the radial distribution functions.

    fname_app: str
        Appendix of file names.

    fldr : str
        Folder containing dumps.

    no_bins : int
        Number of bins.

    no_dumps : int
        Number of dumps.

    no_grs : int
        Number of :math:`g_{ij}(r)` pairs.

    no_species : int
        Number of species.

    no_steps : int
        Total number of steps for which the RDF has been calculated.

    species_np: array
        Array of integers with the number of particles for each species.

    species_names : list
        Names of particle species.

    tot_no_ptcls : int
        Total number of particles.

    dr_rdf : float
        Size of each bin.
    """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.dataframe = None
        self.no_bins = params.PostProcessing.rdf_nbins  # number of ka values
        self.fldr = params.control.checkpoint_dir
        self.job_id = params.control.fname_app
        self.filename_csv = os.path.join(self.fldr, "RadialDistributionFunction_" + params.control.fname_app + ".csv")
        self.dump_step = params.control.dump_step
        self.no_dumps = len(os.listdir(params.control.dump_dir))
        self.no_species = len(params.species)
        self.no_grs = int(params.num_species * (params.num_species + 1) / 2)
        self.tot_no_ptcls = params.total_num_ptcls

        self.no_steps = params.control.Nsteps
        self.a_ws = params.aws
        self.dr_rdf = params.potential.rc / self.no_bins / self.a_ws
        self.box_volume = params.box_volume / self.a_ws ** 3
        self.box_lengths = np.array([params.Lx / params.aws, params.Ly / params.aws, params.Lz / params.aws])
        self.species_np = np.zeros(self.no_species)  # Number of particles of each species
        self.species_names = []

        for i, sp in enumerate(params.species):
            self.species_np[i] = sp.num
            self.species_names.append(sp.name)

    def save(self, rdf_hist):
        """
        Parameters
        ----------
        rdf_hist : array
            Histogram of the radial distribution function.

        """
        # Initialize all the workhorse arrays
        ra_values = np.zeros(self.no_bins)
        bin_vol = np.zeros(self.no_bins)
        pair_density = np.zeros((self.no_species, self.no_species))
        gr = np.zeros((self.no_bins, self.no_grs))

        # No. of pairs per volume
        for i in range(self.no_species):
            pair_density[i, i] = self.species_np[i] * (self.species_np[i] - 1) / (2.0 * self.box_volume)
            for j in range(i + 1, self.no_species):
                pair_density[i, j] = self.species_np[i] * self.species_np[j] / self.box_volume
        # Calculate each bin's volume
        sphere_shell_const = 4.0 * np.pi / 3.0
        bin_vol[0] = sphere_shell_const * self.dr_rdf ** 3
        for ir in range(1, self.no_bins):
            r1 = ir * self.dr_rdf
            r2 = (ir + 1) * self.dr_rdf
            bin_vol[ir] = sphere_shell_const * (r2 ** 3 - r1 ** 3)
            ra_values[ir] = (ir + 0.5) * self.dr_rdf

        data = {"ra values": ra_values}
        self.dataframe = pd.DataFrame(data)

        gr_ij = 0
        for i in range(self.no_species):
            for j in range(i, self.no_species):
                if j == i:
                    pair_density[i, j] *= 2.0
                for ibin in range(self.no_bins):
                    gr[ibin, gr_ij] = (rdf_hist[ibin, i, j] + rdf_hist[ibin, j, i]) / (bin_vol[ibin]
                                                                                       * pair_density[i, j]
                                                                                       * self.no_steps)

                self.dataframe['{}-{} RDF'.format(self.species_names[i], self.species_names[j])] = gr[:, gr_ij]
                gr_ij += 1

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')

    def parse(self):
        """
        Grab the pandas dataframe from the saved csv file.
        """
        self.dataframe = pd.read_csv(self.filename_csv, index_col=False)

    def plot(self, show=False):
        """
        Plot :math: `g_{ij}(r)` and save the figure.

        Parameters
        ----------
        show : bool
            Flag for prompting the plot to screen. Default=False
        """
        self.dataframe = pd.read_csv(self.filename_csv, index_col=False)

        indx = 0
        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        for i in range(self.no_species):
            for j in range(i, self.no_species):
                subscript = self.species_names[i] + self.species_names[j]
                ax.plot(self.dataframe["ra values"],
                        self.dataframe["{}-{} RDF".format(self.species_names[i], self.species_names[j])],
                        label=r'$g_{' + subscript + '} (r)$')
                indx += 1
        ax.grid(True, alpha=0.3)
        if self.no_species > 2:
            ax.legend(loc='best', ncol=(self.no_species - 1))
        else:
            ax.legend(loc='best')

        ax.set_ylabel(r'$g(r)$')
        ax.set_xlabel(r'$r/a$')
        # ax.set_ylim(0, 5)
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, 'RDF_' + self.job_id + '.png'))
        if show:
            fig.show()


class StaticStructureFactor:
    """ Static Structure Factors :math:`S_{ij}(k)`.

    Parameters
    ----------
    params : object
        Simulation's parameters

    Attributes
    ----------
    a_ws : float
        Wigner-Seitz radius.

    box_lengths : array
        Array with box length in each direction.

    dataframe : dict
        Pandas dataframe. It contains all the :math:`S_{ij}(k)` and :math:`ka`.

    dump_step : int
        Dump step frequency.

    filename_csv: str
        Name of output files.

    fname_app: str
        Appendix of filenames.

    fldr : str
        Folder containing dumps.

    no_dumps : int
        Number of dumps.

    no_species : int
        Number of species.

    no_Sk : int
        Number of :math: `S_{ij}(k)` pairs.

    species_np: array
        Array of integers with the number of particles for each species.

    species_names : list
        Names of particle species.

    tot_no_ptcls : int
        Total number of particles.

    ptcls_fldr : str
        Directory of Sarkas dumps.

    k_fldr : str
        Directory of :math:`k`-space fluctuations.

    nkt_file : str
        Name of file containing :math:`n(k,t)` of each species.

    k_file : str
        Name of file containing ``k_list``, ``k_counts``, ``ka_values``.

    k_list : list
        List of all possible :math:`k` vectors with their corresponding magnitudes and indexes.

    k_counts : array
        Number of occurrences of each :math:`k` magnitude.

    ka_values : array
        Magnitude of each allowed :math:`ka` vector.

    no_ka_values: int
        Length of ``ka_values`` array.
    """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.dataframe = None
        self.fldr = params.control.checkpoint_dir
        self.job_id = params.control.fname_app
        self.ptcls_fldr = params.control.dump_dir
        self.k_fldr = os.path.join(self.fldr, "k_space_data")
        self.k_file = os.path.join(self.k_fldr, "k_arrays.npz")
        self.nkt_file = os.path.join(self.k_fldr, "nkt.npy")

        self.filename_csv = os.path.join(self.fldr, "StaticStructureFunction_" + self.job_id + ".csv")
        self.dump_step = params.control.dump_step
        self.no_dumps = len(os.listdir(params.control.dump_dir))
        self.no_species = len(params.species)
        self.tot_no_ptcls = params.total_num_ptcls

        if len(params.PostProcessing.ssf_no_ka_values) == 0:
            self.no_ka = np.array([params.PostProcessing.ssf_no_ka_values,
                                   params.PostProcessing.ssf_no_ka_values,
                                   params.PostProcessing.ssf_no_ka_values], dtype=int)
        else:
            self.no_ka = params.PostProcessing.ssf_no_ka_values  # number of ka values

        self.no_Sk = int(self.no_species * (self.no_species + 1) / 2)
        self.a_ws = params.aws
        self.box_lengths = np.array([params.Lx, params.Ly, params.Lz])
        self.species_np = np.zeros(self.no_species, dtype=int)
        self.species_names = []

        for i, sp in enumerate(params.species):
            self.species_np[i] = sp.num
            self.species_names.append(sp.name)

    def parse(self):
        """
        Grab the pandas dataframe from the saved csv file. If file does not exist call ``compute``.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            print("\nFile {} not found!".format(self.filename_csv))
            print("\nComputing S(k) now")
            self.compute()

    def compute(self):
        """
        Calculate all :math:`S_{ij}(k)`, save them into a Pandas dataframe, and write them to a csv.
        """
        # Parse nkt otherwise calculate it
        try:
            nkt = np.load(self.nkt_file)
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]
            self.no_ka_values = len(self.ka_values)
            print("n(k,t) Loaded")
        except FileNotFoundError:
            self.k_list, self.k_counts, k_unique = kspace_setup(self.no_ka, self.box_lengths)
            self.ka_values = 2.0 * np.pi * k_unique * self.a_ws
            self.no_ka_values = len(self.ka_values)

            if not (os.path.exists(self.k_fldr)):
                os.mkdir(self.k_fldr)

            np.savez(self.k_file,
                     k_list=self.k_list,
                     k_counts=self.k_counts,
                     ka_values=self.ka_values)

            nkt = calc_nkt(self.ptcls_fldr, self.no_dumps, self.dump_step, self.species_np, self.k_list)
            np.save(self.nkt_file, nkt)

        data = {"ka values": self.ka_values}
        self.dataframe = pd.DataFrame(data)

        print("Calculating S(k) ...")
        Sk_all = calc_Sk(nkt, self.k_list, self.k_counts, self.species_np, self.no_dumps)
        Sk = np.mean(Sk_all, axis=-1)
        Sk_err = np.std(Sk_all, axis=-1)

        sp_indx = 0
        for sp_i in range(self.no_species):
            for sp_j in range(sp_i, self.no_species):
                column = "{}-{} SSF".format(self.species_names[sp_i], self.species_names[sp_j])
                err_column = "{}-{} SSF Errorbar".format(self.species_names[sp_i], self.species_names[sp_j])
                self.dataframe[column] = Sk[sp_indx, :]
                self.dataframe[err_column] = Sk_err[sp_indx, :]

                sp_indx += 1

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')

        return

    def plot(self, errorbars=False, show=False):
        """
        Plot :math:`S_{ij}(k)` and save the figure.

        Parameters
        ----------
        show : bool
            Flag to prompt the figure to screen. Default=False.

        errorbars : bool
            Plot errorbars. Default = False.

        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            self.compute()

        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        for i in range(self.no_species):
            for j in range(i, self.no_species):
                subscript = self.species_names[i] + self.species_names[j]
                if errorbars:
                    ax.errorbar(self.dataframe["ka values"],
                                self.dataframe["{}-{} SSF".format(self.species_names[i], self.species_names[j])],
                                yerr=self.dataframe[
                                    "{}-{} SSF Errorbar".format(self.species_names[i], self.species_names[j])],
                                ls='--', marker='o', label=r'$S_{ ' + subscript + '} (k)$')
                else:
                    ax.plot(self.dataframe["ka values"],
                            self.dataframe["{}-{} SSF".format(self.species_names[i], self.species_names[j])],
                            label=r'$S_{ ' + subscript + '} (k)$')

        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right')
        ax.set_ylabel(r'$S(k)$')
        ax.set_xlabel(r'$ka$')
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, 'StaticStructureFactor_' + self.job_id + '.png'))
        if show:
            fig.show()


class Thermodynamics:
    """
    Thermodynamic functions.

    Parameters
    ----------
    params : object
        Simulation's parameters

    Attributes
    ----------
    a_ws : float
        Wigner-Seitz radius.

    box_volume: float
        Box Volume

    dataframe : pandas DataFrame
        It contains all the thermodynamics functions.
        options: "Total Energy", "Potential Energy", "Kinetic Energy", "Temperature", "time", "Pressure",
        "Pressure Tensor ACF", "Pressure Tensor", "Gamma", "{species name} Temperature",
        "{species name} Kinetic Energy".

    dump_step : int
        Dump step frequency.

    filename_csv : str
        Name of csv output file.

    fldr : str
        Folder containing dumps.

    eV2K : float
        Conversion factor from eV to Kelvin.

    no_dim : int
        Number of non-zero dimensions.

    no_dumps : int
        Number of dumps.

    no_species : int
        Number of species.

    species_np: array
        Array of integers with the number of particles for each species.

    species_names : list
        Names of particle species.

    species_masses : list
        Names of particle species.

    tot_no_ptcls : int
        Total number of particles.

    wp : float
        Plasma frequency.

    kB : float
        Boltzmann constant.

    units : str
        System of units used in the simulation. mks or cgs.
    """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.dataframe = None
        self.fldr = params.control.checkpoint_dir
        self.ptcls_dumps = params.control.dump_dir
        self.job_id = params.control.fname_app
        self.dump_step = params.control.dump_step
        self.no_dumps = len(os.listdir(params.control.dump_dir))
        self.no_dim = params.dimensions
        self.units = params.control.units
        self.dt = params.control.dt
        self.potential = params.potential.type
        self.thermostat = params.thermostat.type
        self.thermostat_tau = params.thermostat.tau
        self.F_err = params.pppm.F_err
        self.Nsteps = params.control.Nsteps
        if params.load_method == "restart":
            self.restart_sim = True
        else:
            self.restart_sim = False
        self.box_lengths = params.Lv
        self.box_volume = params.box_volume
        self.tot_no_ptcls = params.total_num_ptcls

        self.no_species = len(params.species)
        self.species_np = np.zeros(self.no_species)
        self.species_names = []
        self.species_masses = np.zeros(self.no_species)
        self.species_dens = np.zeros(self.no_species)
        for i, sp in enumerate(params.species):
            self.species_np[i] = sp.num
            self.species_names.append(sp.name)
            self.species_masses[i] = sp.mass
            self.species_dens[i] = sp.num_density
        # Output file with Energy and Temperature
        self.filename_csv = os.path.join(self.fldr, "Thermodynamics_" + self.job_id + '.csv')
        # Constants
        self.wp = params.wp
        self.kB = params.kB
        self.eV2K = params.eV2K
        self.a_ws = params.aws
        self.T = params.T_desired
        self.Gamma_eff = params.potential.Gamma_eff

    def compute_pressure_quantities(self):
        """
        Calculate Pressure, Pressure Tensor, Pressure Tensor Auto Correlation Function.
        """
        pos = np.zeros((self.no_dim, self.tot_no_ptcls))
        vel = np.zeros((self.no_dim, self.tot_no_ptcls))
        acc = np.zeros((self.no_dim, self.tot_no_ptcls))

        pressure = np.zeros(self.no_dumps)
        pressure_tensor_temp = np.zeros((3, 3, self.no_dumps))

        # Collect particles' positions, velocities and accelerations
        for it in range(int(self.no_dumps)):
            dump = int(it * self.dump_step)

            data = load_from_restart(self.ptcls_dumps, dump)
            pos[0, :] = data["pos"][:, 0]
            pos[1, :] = data["pos"][:, 1]
            pos[2, :] = data["pos"][:, 2]

            vel[0, :] = data["vel"][:, 0]
            vel[1, :] = data["vel"][:, 1]
            vel[2, :] = data["vel"][:, 2]

            acc[0, :] = data["acc"][:, 0]
            acc[1, :] = data["acc"][:, 1]
            acc[2, :] = data["acc"][:, 2]

            pressure[it], pressure_tensor_temp[:, :, it] = calc_pressure_tensor(pos, vel, acc, self.species_masses,
                                                                                self.species_np, self.box_volume)

        self.dataframe["Pressure"] = pressure
        self.dataframe["Pressure ACF"] = autocorrelationfunction_1D(pressure)

        if self.no_dim == 3:
            dim_lbl = ['x', 'y', 'z']

        # Calculate the acf of the pressure tensor
        for i, ax1 in enumerate(dim_lbl):
            for j, ax2 in enumerate(dim_lbl):
                self.dataframe["Pressure Tensor {}{}".format(ax1, ax2)] = pressure_tensor_temp[i, j, :]
                pressure_tensor_acf_temp = autocorrelationfunction_1D(pressure_tensor_temp[i, j, :])
                self.dataframe["Pressure Tensor ACF {}{}".format(ax1, ax2)] = pressure_tensor_acf_temp

        # Save the pressure acf to file
        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')

    def compute_pressure_from_rdf(self, r, gr, potential, potential_matrix):
        """
        Calculate the Pressure using the radial distribution function

        Parameters
        ----------
        potential: str
            Potential used in the simulation.

        potential_matrix: ndarray
            Potential parameters.

        r : array
            Particles' distances.

        gr : array
            Pair distribution function.

        Returns
        -------
        pressure : float
            Pressure divided by :math:`k_BT`.

        """
        r *= self.a_ws
        r2 = r * r
        r3 = r2 * r

        if potential == "Coulomb":
            dv_dr = - 1.0 / r2
            # Check for finiteness of first element when r[0] = 0.0
            if not np.isfinite(dv_dr[0]):
                dv_dr[0] = dv_dr[1]
        elif potential == "Yukawa":
            pass
        elif potential == "QSP":
            pass
        else:
            raise ValueError('Unknown potential')

        # No. of independent g(r)
        T = np.mean(self.dataframe["Temperature"])
        pressure = self.kB * T - 2.0 / 3.0 * np.pi * self.species_dens[0] \
                   * potential_matrix[1, 0, 0] * np.trapz(dv_dr * r3 * gr, x=r)
        pressure *= self.species_dens[0]

        return pressure

    def plot(self, quantity="Total Energy", show=False):
        """
        Plot ``quantity`` vs time and save the figure with appropriate name.

        Parameters
        ----------
        show : bool
            Flag for displaying figure.

        quantity : str
            Quantity to plot. Default = Total Energy.
        """

        self.dataframe = pd.read_csv(self.filename_csv, index_col=False)

        plt.style.use('MSUstyle')

        if quantity[:8] == "Pressure":
            if not "Pressure" in self.dataframe.columns:
                print("Calculating Pressure quantities ...")
                self.compute_pressure_quantities()

        xmul, ymul, xpref, ypref, xlbl, ylbl = plot_labels(self.dataframe["Time"],
                                                               self.dataframe[quantity],
                                                               "Time", quantity, self.units)
        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        yq = {"Total Energy": r"$E_{tot}(t)$", "Kinetic Energy": r"$K_{tot}(t)$", "Potential Energy": r"$U_{tot}(t)$",
                "Temperature": r"$T(t)$",
                "Pressure Tensor ACF": r'$P_{\alpha\beta} = \langle P_{\alpha\beta}(0)P_{\alpha\beta}(t)\rangle$',
                "Pressure Tensor": r"$P_{\alpha\beta}(t)$", "Gamma": r"$\Gamma(t)$", "Pressure": r"$P(t)$"}
        dim_lbl = ['x', 'y', 'z']

        if quantity == "Pressure Tensor ACF":
            for i, dim1 in enumerate(dim_lbl):
                for j, dim2 in enumerate(dim_lbl):
                    ax.plot(self.dataframe["Time"] * xmul,
                            self.dataframe["Pressure Tensor ACF {}{}".format(dim1, dim2)] /
                            self.dataframe["Pressure Tensor ACF {}{}".format(dim1, dim2)][0],
                            label=r'$P_{' + dim1 + dim2 + '} (t)$')
            ax.set_xscale('log')
            ax.legend(loc='best', ncol=3)
            ax.set_ylim(-1, 1.5)

        elif quantity == "Pressure Tensor":
            for i, dim1 in enumerate(dim_lbl):
                for j, dim2 in enumerate(dim_lbl):
                    ax.plot(self.dataframe["Time"] * xmul,
                            self.dataframe["Pressure Tensor {}{}".format(dim1, dim2)] * ymul,
                            label=r'$P_{' + dim1 + dim2 + '} (t)$')
            ax.set_xscale('log')
            ax.legend(loc='best', ncol=3)
        else:
            ax.plot(self.dataframe["Time"] * xmul, self.dataframe[quantity] * ymul)

        ax.grid(True, alpha=0.3)
        ax.set_ylabel(yq[quantity] + ylbl)
        ax.set_xlabel(r'Time' + xlbl)
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, quantity + '_' + self.job_id + '.png'))
        if show:
            fig.show()

    def parse(self):
        """
        Grab the pandas dataframe from the saved csv file.
        """
        self.dataframe = pd.read_csv(self.filename_csv, index_col=False)

    def statistics(self, quantity="Total Energy", max_no_divisions=100, show=False):
        """
        ToDo:
        Parameters
        ----------
        quantity
        max_no_divisions
        show

        Returns
        -------

        """
        self.parse()
        run_avg = self.dataframe[quantity].mean()
        run_std = self.dataframe[quantity].std()

        observable = np.array(self.dataframe[quantity])
        # Loop over the blocks
        tau_blk, sigma2_blk, statistical_efficiency = calc_statistical_efficiency(observable,
                                                                                  run_avg, run_std,
                                                                                  max_no_divisions, self.no_dumps)
        # Plot the statistical efficiency
        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        ax.plot(1 / tau_blk[2:], statistical_efficiency[2:], '--o', label=quantity)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best')
        ax.set_xscale('log')
        ax.set_ylabel(r'$s(\tau_{\rm{blk}})$')
        ax.set_xlabel(r'$1/\tau_{\rm{blk}}$')
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, quantity + 'StatisticalEfficiency_' + self.job_id + '.png'))

        if show:
            fig.show()

        return

    def temp_energy_plot(self, params, show=False):
        """
        Plot Temperature and Energy as a function of time with their cumulative sum and average.

        Parameters
        ----------
        show: bool
            Flag for displaying the figure.

        params : object
           Simulation's parameters.

        """
        self.parse()

        fig = plt.figure(figsize=(16, 9))
        gs = GridSpec(4, 8)
        # quantity = "Temperature"
        self.no_dumps = len(self.dataframe["Time"])
        nbins = int(0.05 * self.no_dumps)

        Info_plot = fig.add_subplot(gs[0:4, 0:2])

        T_hist_plot = fig.add_subplot(gs[1:4, 2])
        T_delta_plot = fig.add_subplot(gs[0, 3:5])
        T_main_plot = fig.add_subplot(gs[1:4, 3:5])

        E_delta_plot = fig.add_subplot(gs[0, 5:7])
        E_main_plot = fig.add_subplot(gs[1:4, 5:7])
        E_hist_plot = fig.add_subplot(gs[1:4, 7])

        # Temperature plots
        xmul, ymul, xprefix, yprefix, xlbl, ylbl = plot_labels(self.dataframe["Time"],
                                                               self.dataframe["Temperature"], "Time",
                                                               "Temperature", params.control.units)
        T_cumavg = self.dataframe["Temperature"].cumsum() / [i for i in range(1, self.no_dumps + 1)]

        T_main_plot.plot(xmul * self.dataframe["Time"], ymul * self.dataframe["Temperature"], alpha=0.7)
        T_main_plot.plot(xmul * self.dataframe["Time"], ymul * T_cumavg, label='Cum Avg')
        T_main_plot.axhline(ymul * params.T_desired, ls='--', c='r', alpha=0.7, label='Desired T')

        Delta_T = (self.dataframe["Temperature"] - self.T) * 100 / self.T
        Delta_T_cum_avg = Delta_T.cumsum() / [i for i in range(1, self.no_dumps + 1)]
        T_delta_plot.plot(self.dataframe["Time"], Delta_T, alpha=0.5)
        T_delta_plot.plot(self.dataframe["Time"], Delta_T_cum_avg, alpha=0.8)

        T_delta_plot.get_xaxis().set_ticks([])
        T_delta_plot.set_ylabel(r'Deviation [%]')
        T_delta_plot.tick_params(labelsize=12)
        T_main_plot.tick_params(labelsize=14)
        T_main_plot.legend(loc='best')
        T_main_plot.set_ylabel("Temperature" + ylbl)
        T_main_plot.set_xlabel("Time" + xlbl)
        T_hist_plot.hist(self.dataframe['Temperature'], bins=nbins, density=True, orientation='horizontal',
                         alpha=0.75)
        T_hist_plot.get_xaxis().set_ticks([])
        T_hist_plot.get_yaxis().set_ticks([])
        T_hist_plot.set_xlim(T_hist_plot.get_xlim()[::-1])

        # Energy plots
        xmul, ymul, xprefix, yprefix, xlbl, ylbl = plot_labels(self.dataframe["Time"],
                                                               self.dataframe["Total Energy"], "Time",
                                                               "Total Energy", params.control.units)
        E_cumavg = self.dataframe["Total Energy"].cumsum() / [i for i in range(1, self.no_dumps + 1)]

        E_main_plot.plot(xmul * self.dataframe["Time"], ymul * self.dataframe["Total Energy"], alpha=0.7)
        E_main_plot.plot(xmul * self.dataframe["Time"], ymul * E_cumavg, label='Cum Avg')
        E_main_plot.axhline(ymul * self.dataframe["Total Energy"].mean(), ls='--', c='r', alpha=0.7, label='Avg')

        Delta_E = (self.dataframe["Total Energy"] - self.dataframe["Total Energy"][0]) * 100 / \
                  self.dataframe["Total Energy"][0]
        Delta_E_cum_avg = Delta_E.cumsum() / [i for i in range(1, self.no_dumps + 1)]
        E_delta_plot.plot(self.dataframe["Time"], Delta_E, alpha=0.5)
        E_delta_plot.plot(self.dataframe["Time"], Delta_E_cum_avg, alpha=0.8)

        E_delta_plot.get_xaxis().set_ticks([])
        E_delta_plot.set_ylabel(r'Deviation [%]')
        E_delta_plot.tick_params(labelsize=12)
        E_main_plot.tick_params(labelsize=14)
        E_main_plot.legend(loc='best')
        E_main_plot.set_ylabel("Total Energy" + ylbl)
        E_main_plot.set_xlabel("Time" + xlbl)
        E_hist_plot.hist(xmul * self.dataframe['Total Energy'], bins=nbins, density=True,
                         orientation='horizontal', alpha=0.75)
        E_hist_plot.get_xaxis().set_ticks([])
        E_hist_plot.get_yaxis().set_ticks([])

        xmul, ymul, xprefix, yprefix, xlbl, ylbl = plot_labels(np.array([self.dt]),
                                                               self.dataframe["Temperature"], "Time",
                                                               "Temperature", params.control.units)
        Info_plot.axis([0, 10, 0, 10])
        Info_plot.grid(False)
        fsz = 14
        Info_plot.text(0., 10, "Job ID: {}".format(self.job_id), fontsize=fsz)
        Info_plot.text(0., 9.5, "No. of species = {}".format(len(self.species_np)), fontsize=fsz)
        y_coord = 9.0
        for isp, sp in enumerate(self.species_names):
            Info_plot.text(0., y_coord, "Species {} : {}".format(isp + 1, sp), fontsize=fsz)
            Info_plot.text(0.0, y_coord - 0.5, "  No. of particles = {} ".format(self.species_np[isp]), fontsize=fsz)
            Info_plot.text(0.0, y_coord - 1., "  Temperature = {:1.2f} {}".format(
                ymul * self.dataframe['{} Temperature'.format(sp)].iloc[-1],
                ylbl), fontsize=fsz)
            y_coord -= 1.5

        y_coord -= 0.25
        Info_plot.text(0., y_coord, "Total $N$ = {}".format(params.total_num_ptcls), fontsize=fsz)
        Info_plot.text(0., y_coord - 0.5, "Thermostat: {}".format(params.thermostat.type), fontsize=fsz)
        Info_plot.text(0., y_coord - 1., "Berendsen rate = {:1.2f}".format(1.0 / params.thermostat.tau), fontsize=fsz)
        Info_plot.text(0., y_coord - 1.5, "Potential: {}".format(params.potential.type), fontsize=fsz)
        if params.pppm.on:
            Info_plot.text(0., y_coord - 2., "Tot Force Error = {:1.4e}".format(params.pppm.F_err), fontsize=fsz)
        else:
            Info_plot.text(0., y_coord - 2., "Tot Force Error = {:1.4e}".format(params.PP_err), fontsize=fsz)

        Info_plot.text(0., y_coord - 2.5, "Timestep = {:1.4f} {}".format(xmul * params.control.dt, xlbl), fontsize=fsz)
        Info_plot.text(0., y_coord - 3., "Tot Prod. steps = {}".format(params.control.Nsteps))
        Info_plot.text(0., y_coord - 4., "{:1.2f} % Production Completed".format(
            100 * self.dump_step * (self.no_dumps - 1) / params.control.Nsteps), fontsize=fsz)

        Info_plot.axis('off')
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, 'EnsembleCheckPlot_' + self.job_id + '.png'))
        if show:
            fig.show()


class Thermalization:
    """
    Thermalization tool for checking whether the system is thermalizing.

    Parameters
    ----------
    params : object
        Simulation's parameters

    Attributes
    ----------
    a_ws : float
        Wigner-Seitz radius.

    box_volume: float
        Box Volume

    dataframe : pandas dataframe
        It contains all the thermodynamics functions.
        options: "Total Energy", "Potential Energy", "Kinetic Energy", "Temperature", "time", "Pressure",
        "Pressure Tensor ACF", "Pressure Tensor", "Gamma", "{species name} Temperature",
        "{species name} Kinetic Energy".

    dump_step : int
        Dump step frequency.

    filename_csv : str
        Name of csv output file.

    fldr : str
        Folder containing dumps.

    eV2K : float
        Conversion factor from eV to Kelvin.

    no_dim : int
        Number of non-zero dimensions.

    no_dumps : int
        Number of dumps.

    no_species : int
        Number of species.

    species_np: array
        Array of integers with the number of particles for each species.

    species_names : list
        Names of particle species.

    species_masses : list
        Names of particle species.

    tot_no_ptcls : int
        Total number of particles.

    wp : float
        Plasma frequency.

    kB : float
        Boltzmann constant.

    units : str
        System of units used in the simulation. mks or cgs.

    F_err : float
        Dimensionless force error.

    Nsteps: int
        Total number of thermalization/equilibration steps.

    potential:
    """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.fldr = params.control.therm_dir
        self.dump_dir = os.path.join(self.fldr, "dumps")
        self.job_id = params.control.fname_app
        self.dump_step = params.control.therm_dump_step
        self.no_dumps = len(os.listdir(params.control.therm_dir))
        self.no_dim = params.dimensions
        self.units = params.control.units
        self.dt = params.control.dt
        self.potential = params.potential.type
        self.thermostat = params.thermostat.type
        self.thermostat_tau = params.thermostat.tau
        if not hasattr(params.pppm, 'F_err'):
            self.F_err = params.PP_err
        else:
            self.F_err = params.pppm.F_err
        self.Nsteps = params.control.Neq
        if params.load_method == "restart":
            self.restart_sim = True
        else:
            self.restart_sim = False
        self.box_lengths = params.Lv
        self.box_volume = params.box_volume
        self.tot_no_ptcls = params.total_num_ptcls

        self.no_species = len(params.species)
        self.species_np = np.zeros(self.no_species)
        self.species_names = []
        self.species_masses = np.zeros(self.no_species)
        self.species_dens = np.zeros(self.no_species)
        for i, sp in enumerate(params.species):
            self.species_np[i] = sp.num
            self.species_names.append(sp.name)
            self.species_masses[i] = sp.mass
            self.species_dens[i] = sp.num_density
        # Output file with Energy and Temperature
        self.filename_csv = os.path.join(self.fldr, "Thermalization_" + self.job_id + '.csv')
        # Constants
        self.wp = params.wp
        self.kB = params.kB
        self.eV2K = params.eV2K
        self.a_ws = params.aws
        self.T = params.T_desired
        self.Gamma_eff = params.potential.Gamma_eff

    def parse(self):
        """
        Grab the pandas dataframe from the saved csv file.
        """
        self.dataframe = pd.read_csv(self.filename_csv, index_col=False)

    def statistics(self, quantity="Total Energy", max_no_divisions=100, show=False):

        self.parse()
        run_avg = self.dataframe[quantity].mean()
        run_std = self.dataframe[quantity].std()

        observable = np.array(self.dataframe[quantity])
        # Loop over the blocks
        tau_blk, sigma2_blk, statistical_efficiency = calc_statistical_efficiency(observable,
                                                                                  run_avg, run_std,
                                                                                  max_no_divisions, self.no_dumps)
        # Plot the statistical efficiency
        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        ax.plot(1 / tau_blk[2:], statistical_efficiency[2:], '--o', label=quantity)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best')
        ax.set_xscale('log')
        ax.set_ylabel(r'$s(\tau_{\rm{blk}})$')
        ax.set_xlabel(r'$1/\tau_{\rm{blk}}$')
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, quantity + 'StatisticalEfficiency_' + self.job_id + '.png'))

        if show:
            fig.show()

        return

    def hermite_plot(self, params, show=False):
        """
        Calculate Hermite Coefficients and save the plots.

        Parameters
        ----------
        params : object
            Simulation's parameters

        show: bool
            Flag for showing plots

        Returns
        -------
        hc: object
            Hermite Coefficient object.

        """
        hc = HermiteCoefficients(params)
        hc.dump_dir = self.dump_dir
        hc.no_dumps = len(os.listdir(self.dump_dir))
        hc.compute()
        hc.plot(show)

        return hc

    def moment_ratios_plot(self, params, show=False):
        """
        Calculate, plot, and save velocity moments.

        Parameters
        ----------
        params : object
           Simulation's parameters.

        show: bool
            Flag for showing plots to screen

        Returns
        -------
        vm: object
            Velocity moments object.

        """
        vm = VelocityMoments(params)
        vm.dump_dir = self.dump_dir
        vm.no_dumps = len(os.listdir(self.dump_dir))
        vm.compute()
        vm.plot_ratios(show)

        return vm

    def temp_energy_plot(self, params, show=False):
        """
        Plot Temperature and Energy as a function of time with their cumulative sum and average.

        Parameters
        ----------
        show: bool
            Flag for displaying the figure.

        params : object
           Simulation's parameters.

        """
        self.parse()

        fig = plt.figure(figsize=(16, 9))
        gs = GridSpec(4, 8)
        # quantity = "Temperature"
        self.no_dumps = len(self.dataframe["Time"])
        nbins = int(0.05 * self.no_dumps)

        Info_plot = fig.add_subplot(gs[0:4, 0:2])

        T_hist_plot = fig.add_subplot(gs[1:4, 2])
        T_delta_plot = fig.add_subplot(gs[0, 3:5])
        T_main_plot = fig.add_subplot(gs[1:4, 3:5])

        E_delta_plot = fig.add_subplot(gs[0, 5:7])
        E_main_plot = fig.add_subplot(gs[1:4, 5:7])
        E_hist_plot = fig.add_subplot(gs[1:4, 7])

        # Temperature plots
        xmul, ymul, xprefix, yprefix, xlbl, ylbl = plot_labels(self.dataframe["Time"],
                                                               self.dataframe["Temperature"], "Time",
                                                               "Temperature", self.units)
        T_cumavg = self.dataframe["Temperature"].cumsum() / [i for i in range(1, self.no_dumps + 1)]

        T_main_plot.plot(xmul * self.dataframe["Time"], ymul * self.dataframe["Temperature"], alpha=0.7)
        T_main_plot.plot(xmul * self.dataframe["Time"], ymul * T_cumavg, label='Cum Avg')
        T_main_plot.axhline(ymul * self.T, ls='--', c='r', alpha=0.7, label='Desired T')

        Delta_T = (self.dataframe["Temperature"] - self.T) * 100 / self.T
        Delta_T_cum_avg = Delta_T.cumsum() / [i for i in range(1, self.no_dumps + 1)]
        T_delta_plot.plot(self.dataframe["Time"], Delta_T, alpha=0.5)
        T_delta_plot.plot(self.dataframe["Time"], Delta_T_cum_avg, alpha=0.8)

        T_delta_plot.get_xaxis().set_ticks([])
        T_delta_plot.set_ylabel(r'Deviation [%]')
        T_delta_plot.tick_params(labelsize=12)
        T_main_plot.tick_params(labelsize=14)
        T_main_plot.legend(loc='best')
        T_main_plot.set_ylabel("Temperature" + ylbl)
        T_main_plot.set_xlabel("Time" + xlbl)
        T_hist_plot.hist(self.dataframe['Temperature'], bins=nbins, density=True, orientation='horizontal',
                         alpha=0.75)
        T_hist_plot.get_xaxis().set_ticks([])
        T_hist_plot.get_yaxis().set_ticks([])
        T_hist_plot.set_xlim(T_hist_plot.get_xlim()[::-1])

        # Energy plots
        xmul, ymul, xprefix, yprefix, xlbl, ylbl = plot_labels(self.dataframe["Time"],
                                                               self.dataframe["Total Energy"], "Time",
                                                               "Total Energy", self.units)
        E_cumavg = self.dataframe["Total Energy"].cumsum() / [i for i in range(1, self.no_dumps + 1)]

        E_main_plot.plot(xmul * self.dataframe["Time"], ymul * self.dataframe["Total Energy"], alpha=0.7)
        E_main_plot.plot(xmul * self.dataframe["Time"], ymul * E_cumavg, label='Cum Avg')
        E_main_plot.axhline(ymul * self.dataframe["Total Energy"].mean(), ls='--', c='r', alpha=0.7, label='Avg')

        Delta_E = (self.dataframe["Total Energy"] - self.dataframe["Total Energy"][0]) * 100 / \
                  self.dataframe["Total Energy"][0]
        Delta_E_cum_avg = Delta_E.cumsum() / [i for i in range(1, self.no_dumps + 1)]
        E_delta_plot.plot(self.dataframe["Time"], Delta_E, alpha=0.5)
        E_delta_plot.plot(self.dataframe["Time"], Delta_E_cum_avg, alpha=0.8)

        E_delta_plot.get_xaxis().set_ticks([])
        E_delta_plot.set_ylabel(r'Deviation [%]')
        E_delta_plot.tick_params(labelsize=12)
        E_main_plot.tick_params(labelsize=14)
        E_main_plot.legend(loc='best')
        E_main_plot.set_ylabel("Total Energy" + ylbl)
        E_main_plot.set_xlabel("Time" + xlbl)
        E_hist_plot.hist(xmul * self.dataframe['Total Energy'], bins=nbins, density=True,
                         orientation='horizontal', alpha=0.75)
        E_hist_plot.get_xaxis().set_ticks([])
        E_hist_plot.get_yaxis().set_ticks([])

        xmul, ymul, xprefix, yprefix, xlbl, ylbl = plot_labels(np.array([self.dt]),
                                                               self.dataframe["Temperature"], "Time",
                                                               "Temperature", params.control.units)
        Info_plot.axis([0, 10, 0, 10])
        Info_plot.grid(False)
        fsz = 14
        Info_plot.text(0., 10, "Job ID: {}".format(self.job_id))
        Info_plot.text(0., 9.5, "No. of species = {}".format(len(self.species_np)))
        y_coord = 9.0
        for isp, sp in enumerate(self.species_names):
            Info_plot.text(0., y_coord, "Species {} : {}".format(isp + 1, sp))
            Info_plot.text(0.0, y_coord - 0.5, "  No. of particles = {} ".format(self.species_np[isp]))
            if self.no_species > 1:
                Info_plot.text(0.0, y_coord - 1., "  Temperature = {:1.2f} {}".format(
                    ymul * self.dataframe['{} Temperature'.format(sp)].iloc[-1], ylbl))
            else:
                Info_plot.text(0.0, y_coord - 1., "  Temperature = {:1.2f} {}".format(
                    ymul * self.dataframe['Temperature'].iloc[-1], ylbl))
            y_coord -= 1.5

        y_coord -= 0.25
        Info_plot.text(0., y_coord, "Total $N$ = {}".format(params.total_num_ptcls))
        Info_plot.text(0., y_coord - 0.5, "Thermostat: {}".format(params.thermostat.type))
        Info_plot.text(0., y_coord - 1., "Berendsen rate = {:1.2f}".format(1.0 / params.thermostat.tau))
        Info_plot.text(0., y_coord - 1.5, "Potential: {}".format(params.potential.type))
        if params.pppm.on:
            Info_plot.text(0., y_coord - 2., "Tot Force Error = {:1.4e}".format(params.pppm.F_err))
        else:
            Info_plot.text(0., y_coord - 2., "Tot Force Error = {:1.4e}".format(params.PP_err))

        Info_plot.text(0., y_coord - 2.5, "Timestep = {:1.4f} {}".format(xmul * params.control.dt, xlbl))
        Info_plot.text(0., y_coord - 3., "Tot Eq. steps = {}".format(params.control.Neq))
        Info_plot.text(0., y_coord - 4., "{:1.2f} % Thermalization Completed".format(
            100 * (self.dump_step * (self.no_dumps - 1)) / params.control.Neq))

        Info_plot.axis('off')
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, 'TempEnergyPlot_' + self.job_id + '.png'))
        if show:
            fig.show()


class Transport:
    """
    Transport Coefficients class

    Parameters
    ----------
    params: object
        Simulation's parameters.

    Attributes
    ----------
    params: object
        Simulation's parameters.

    """

    def __init__(self):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.dataframe = pd.DataFrame()
        self.filename_csv = 'TransportCoefficients.csv'
        pass

    def compute(self, params, quantity="Electrical Conductivity", show=False):
        """
        Calculate the desired transport coefficient

        Parameters
        ----------
        show : bool
            Flag for prompting plots to screen.

        quantity: str
            Desired transport coefficient to calculate.
        """
        self.filename_csv = os.path.join(params.control.checkpoint_dir, self.filename_csv)
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            print("\nFile {} not found!".format(self.filename_csv))

        plt.style.use('MSUstyle')
        if quantity == "Electrical Conductivity":
            J = ElectricCurrent(params)
            J.plot(show)
            sigma = np.zeros(J.no_dumps)
            integrand = np.array(J.dataframe["Total Current ACF"])
            time = np.array(J.dataframe["Time"])
            for it in range(1, J.no_dumps):
                sigma[it] = np.trapz(integrand[:it], x=time[:it]) / 3.0
            self.dataframe["Electrical Conductivity"] = sigma
            # Plot the transport coefficient at different integration times
            fig, ax = plt.subplots(1, 1, figsize=(10, 7))
            ax.plot(time, sigma, label=r'$\sigma (t)$')
            ax.grid(True, alpha=0.3)
            ax.legend(loc='best')
            ax.set_ylabel(r'$\sigma(t)$')
            ax.set_xlabel(r'$\omega_p t$')
            fig.tight_layout()
            fig.savefig(os.path.join(params.control.checkpoint_dir,
                                     'ConductivityPlot_' + params.control.fname_app + '.png'))
            if show:
                fig.show()

        elif quantity == "Diffusion":
            Z = VelocityAutocorrelationFunctions(params)
            Z.plot(show)
            D = np.zeros((params.num_species, Z.no_dumps))
            fig, ax = plt.subplots(1, 1, figsize=(10, 7))
            for i, sp in enumerate(params.species):
                integrand = np.array(Z.dataframe["{} Total Velocity ACF".format(sp.name)])
                time = np.array(Z.dataframe["Time"])
                const = 1.0 / 3.0 / Z.tot_mass_density
                for it in range(1, Z.no_dumps):
                    D[i, it] = const * np.trapz(integrand[:it], x=time[:it])

                # Sk = StaticStructureFactor(self.params)
                # try:
                #     Sk.dataframe = pd.read_csv(Sk.filename_csv, index_col=False)
                # except FileNotFoundError:
                #     Sk.compute()
                # Take the determinant of the matrix
                # Take the limit k --> 0 .

                self.dataframe["{} Diffusion".format(sp.name)] = D[i, :]
                # Find the minimum slope. This would be the ideal value
                # indx = np.gradient(D[i, :]).argmin()
                # lgnd_label = r'$D_{' + sp.name + '} =' + '{:1.4f}$'.format(D[i, indx]) \
                #              + " @ $t = {:2.2f}$".format(time[half_t + indx]*self.params.wp)
                ax.plot(time * params.wp, D[i, :], label=r'$D_{' + sp.name + '}(t)$')
                # ax2.semilogy(time*self.params.wp, -np.gradient(np.gradient(D[i, :])), ls='--', lw=LW - 1,
                #          label=r'$\nabla D_{' + sp.name + '}(t)$')
            # Complete figure
            ax.grid(True, alpha=0.3)
            ax.legend(loc='best')
            ax.set_ylabel(r'$D_{\alpha}(t)/(a^2\omega_{\alpha})$')
            ax.set_xlabel(r'$\omega_p t$')

            # ax2.legend(loc='best')
            # ax2.tick_params(labelsize=FSZ)
            # ax2.set_ylabel(r'$\nabla D_{\alpha}(t)/(a^2\omega_{\alpha})$')

            fig.tight_layout()
            fig.savefig(os.path.join(params.control.checkpoint_dir,
                                     'DiffusionPlot_' + params.control.fname_app + '.png'))
            if show:
                fig.show()

        elif quantity == "Interdiffusion":
            Z = VelocityAutocorrelationFunctions(params)
            Z.plot(show)
            no_int = Z.no_dumps
            no_dij = int(Z.no_species * (Z.no_species - 1) / 2)
            D_ij = np.zeros((no_dij, no_int))

            indx = 0
            for i, sp1 in enumerate(params.species):
                for j in range(i + 1, params.num_species):
                    integrand = np.array(Z.dataframe["{}-{} Total Current ACF".format(sp1.name,
                                                                                      params.species[j].name)])
                    time = np.array(Z.dataframe["Time"])
                    const = 1.0 / (3.0 * params.wp * params.aws ** 2)
                    const /= (sp1.concentration * params.species[j].concentration)
                    for it in range(1, no_int):
                        D_ij[indx, it] = const * np.trapz(integrand[:it], x=time[:it])

                    self.dataframe["{}-{} Inter Diffusion".format(sp1.name,params.species[j].name)] = D_ij[i,:]

        elif quantity == "Viscosity":
            therm = Thermodynamics(params)
            therm.parse()
            time = therm.dataframe["Time"]
            dim_lbl = ['x', 'y', 'z']
            shear_viscosity = np.zeros((params.dimensions, params.dimensions, therm.no_dumps))
            bulk_viscosity = np.zeros(therm.no_dumps)
            const = params.box_volume / params.kB
            if not 'Pressure Tensor ACF xy' in therm.dataframe.columns:
                print('Pressure not yet calculated')
                print("Calculating Pressure quantities ...")
                therm.compute_pressure_quantities()

            xmul, ymul, xpref, ypref, xlbl, ylbl = plot_labels(therm.dataframe["Time"], 1.0,
                                                               "Time", "Pressure", params.control.units)
            # Calculate the acf of the pressure tensor

            fig, axes = plt.subplots(2, 3, figsize=(16, 9))
            for i, ax1 in enumerate(dim_lbl):
                for j, ax2 in enumerate(dim_lbl):
                    integrand = np.array(therm.dataframe["Pressure Tensor ACF {}{}".format(ax1, ax2)]) \
                                / np.array(therm.dataframe["Temperature"])
                    for it in range(1, therm.no_dumps):
                        shear_viscosity[i, j, it] = const * np.trapz(integrand[:it], x=time[:it])

                    self.dataframe["{}{} Shear Viscosity Tensor".format(ax1, ax2)] = shear_viscosity[i, j, :]
                    if "{}{}".format(ax1, ax2) in ["yx", "xy"]:
                        axes[0, 0].semilogx(xmul * therm.dataframe["Time"],
                                            therm.dataframe["Pressure Tensor ACF {}{}".format(ax1, ax2)] /
                                            therm.dataframe["Pressure Tensor ACF {}{}".format(ax1, ax2)][0],
                                            label=r"$P_{" + "{}{}".format(ax1, ax2) + " }(t)$")
                        axes[1, 0].semilogx(xmul * therm.dataframe["Time"],
                                            self.dataframe["{}{} Shear Viscosity Tensor".format(ax1, ax2)],
                                            label=r"$\eta_{ " + "{}{}".format(ax1, ax2) + " }(t)$")
                    elif "{}{}".format(ax1, ax2) in ["xz", "zx"]:
                        axes[0, 1].semilogx(xmul * therm.dataframe["Time"],
                                            therm.dataframe["Pressure Tensor ACF {}{}".format(ax1, ax2)] /
                                            therm.dataframe["Pressure Tensor ACF {}{}".format(ax1, ax2)][0],
                                            label=r"$P_{" + "{}{}".format(ax1, ax2) + " }(t)$")
                        axes[1, 1].semilogx(xmul * therm.dataframe["Time"],
                                            self.dataframe["{}{} Shear Viscosity Tensor".format(ax1, ax2)],
                                            label=r"$\eta_{ " + "{}{}".format(ax1, ax2) + " }(t)$")

                    elif "{}{}".format(ax1, ax2) in ["yz", "zy"]:
                        axes[0, 2].semilogx(xmul * therm.dataframe["Time"],
                                            therm.dataframe["Pressure Tensor ACF {}{}".format(ax1, ax2)] /
                                            therm.dataframe["Pressure Tensor ACF {}{}".format(ax1, ax2)][0],
                                            label=r"$P_{" + "{}{}".format(ax1, ax2) + " }(t)$")
                        axes[1, 2].semilogx(xmul * therm.dataframe["Time"],
                                            self.dataframe["{}{} Shear Viscosity Tensor".format(ax1, ax2)],
                                            label=r"$\eta_{ " + "{}{}".format(ax1, ax2) + " }(t)$")
                axes[0, 0].legend()
                axes[0, 1].legend()
                axes[0, 2].legend()
                axes[1, 0].legend()
                axes[1, 1].legend()
                axes[1, 2].legend()
                axes[1, 0].set_xlabel(r"Time " + xlbl)
                axes[1, 1].set_xlabel(r"Time " + xlbl)
                axes[1, 2].set_xlabel(r"Time " + xlbl)

                axes[0, 0].set_ylabel(r"Pressure Tensor ACF")
                axes[1, 0].set_ylabel(r"Shear Viscosity")

                fig.tight_layout()
                fig.savefig(os.path.join(params.control.checkpoint_dir, "ShearViscosity_Plots.png"))
                if show:
                    fig.show()

            # Calculate Bulk Viscosity
            pressure_acf = autocorrelationfunction_1D(np.array(therm.dataframe["Pressure"])
                                                        - therm.dataframe["Pressure"].mean())
            bulk_integrand = pressure_acf / np.array(therm.dataframe["Temperature"])
            for it in range(1, therm.no_dumps):
                bulk_viscosity[it] = const * np.trapz(bulk_integrand[:it], x=time[:it])

            self.dataframe["Bulk Viscosity"] = bulk_viscosity

            fig, ax = plt.subplots(2, 1)
            ax[0].semilogx(xmul * therm.dataframe["Time"], pressure_acf / pressure_acf[0], label=r"$P(t)$")
            ax[1].semilogx(xmul * therm.dataframe["Time"], self.dataframe["Bulk Viscosity"],
                           label=r"$\eta_{V}(t)$")

            ax[1].set_xlabel(r"Time " + xlbl)
            ax[0].set_ylabel(r"Pressure ACF")
            ax[1].set_ylabel(r"Bulk Viscosity")
            ax[0].legend()
            ax[1].legend()
            fig.tight_layout()
            fig.savefig(os.path.join(params.control.checkpoint_dir, "BulkViscosity_Plots.png"))
            if show:
                fig.show()

        self.dataframe.to_csv("TransportCoefficients.csv", index=False, encoding='utf-8')
        return


class VelocityAutocorrelationFunctions:
    """
    Velocity Auto-correlation function.

    Parameters
    ----------
    params: object
        Simulation's parameters.


    Attributes
    ----------
    a_ws : float
        Wigner-Seitz radius.

    wp : float
        Total plasma frequency.

    dump_step : int
        Dump step frequency.

    dt : float
        Timestep magnitude.

    fldr : str
        Folder containing dumps.

    no_dumps : int
        Number of dumps.

    no_species : int
        Number of species.

    species_np: array
        Array of integers with the number of particles for each species.

    species_names : list
        Names of particle species.

    tot_no_ptcls : int
        Total number of particles.
    """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.dataframe = None
        self.fldr = params.control.checkpoint_dir
        self.dump_dir = params.control.dump_dir
        self.job_id = params.control.fname_app
        self.filename_csv = os.path.join(self.fldr, "VelocityACF_" + self.job_id + '.csv')
        self.dump_step = params.control.dump_step
        self.no_dumps = len(os.listdir(params.control.dump_dir))
        self.no_species = len(params.species)
        self.no_vacf = int(self.no_species * (self.no_species + 1) / 2)
        self.species_names = []
        self.dt = params.control.dt  # No of dump to skip
        self.species_np = np.zeros(self.no_species, dtype=int)
        self.species_masses = np.zeros(self.no_species)
        self.species_dens = np.zeros(self.no_species)
        for i, sp in enumerate(params.species):
            self.species_np[i] = int(sp.num)
            self.species_dens[i] = sp.num_density
            self.species_masses[i] = sp.mass
            self.species_names.append(sp.name)
        self.tot_mass_density = self.species_masses.transpose() @ self.species_dens
        self.tot_no_ptcls = params.total_num_ptcls
        self.wp = params.wp
        self.a_ws = params.aws
        self.dt = params.control.dt
        self.verbose = params.control.verbose

    def parse(self):
        """
        Grab the pandas dataframe from the saved csv file. If file does not exist call ``compute``.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            print("\nFile {} not found!".format(self.filename_csv))
            print("\nComputing VACF now ...")
            self.compute()

    def compute(self, time_averaging=False, it_skip=100):
        """
        Compute the velocity auto-correlation functions.
        """

        # Parse the particles from the dump files
        vel = np.zeros((3, self.tot_no_ptcls, self.no_dumps))
        #
        print("Parsing particles' velocities.")
        time = np.zeros(self.no_dumps)
        for it in tqdm(range(self.no_dumps), disable=(not self.verbose)):
            dump = int(it * self.dump_step)
            time[it] = dump * self.dt
            datap = load_from_restart(self.dump_dir, dump)
            vel[0, :, it] = datap["vel"][:, 0]
            vel[1, :, it] = datap["vel"][:, 1]
            vel[2, :, it] = datap["vel"][:, 2]
        #

        data_dic = {"Time": time}
        self.dataframe = pd.DataFrame(data_dic)
        if time_averaging:
            print("Calculating vacf with time averaging on...")
        else:
            print("Calculating vacf with time averaging off...")
        vacf = calc_vacf(vel, self.species_np, self.species_masses, time_averaging, it_skip)

        # Save to csv
        v_ij = 0
        for sp in range(self.no_species):
            self.dataframe["{} X Velocity ACF".format(self.species_names[sp])] = vacf[v_ij, 0, :]
            self.dataframe["{} Y Velocity ACF".format(self.species_names[sp])] = vacf[v_ij, 1, :]
            self.dataframe["{} Z Velocity ACF".format(self.species_names[sp])] = vacf[v_ij, 2, :]
            self.dataframe["{} Total Velocity ACF".format(self.species_names[sp])] = vacf[v_ij, 3, :]
            for sp2 in range(sp + 1, self.no_species):
                v_ij += 1
                self.dataframe["{}-{} X Current ACF".format(self.species_names[sp],
                                                            self.species_names[sp2])] = vacf[v_ij, 0, :]
                self.dataframe["{}-{} Y Current ACF".format(self.species_names[sp],
                                                            self.species_names[sp2])] = vacf[v_ij, 1, :]
                self.dataframe["{}-{} Z Current ACF".format(self.species_names[sp],
                                                            self.species_names[sp2])] = vacf[v_ij, 2, :]
                self.dataframe["{}-{} Total Current ACF".format(self.species_names[sp],
                                                                self.species_names[sp2])] = vacf[v_ij, 3, :]

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')
        return

    def plot(self, intercurrent=False, show=False):
        """
        Plot the velocity autocorrelation function and save the figure.

        Parameters
        ----------
        show: bool
            Flag for displaying the figure.

        intercurrent: bool
            Flag for plotting inter-species currents instead of vacf.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            self.compute()

        if intercurrent:
            fig, ax = plt.subplots(1, 1)
            for i, sp_name in enumerate(self.species_names):
                for j in range(i + 1, self.no_species):
                    J = self.dataframe["{}-{} Total Current ACF".format(sp_name, self.species_names[j])]
                    ax.plot(self.dataframe["Time"] * self.wp,
                            J / J[0], label=r'$J_{' + sp_name + self.species_names[j] + '} (t)$')
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right')
            ax.set_ylabel(r'$J(t)$', )
            ax.set_xlabel(r'$\omega_p t$')
            ax.set_xscale('log')
            ax.set_ylim(-0.2, 1.2)
            fig.tight_layout()
            fig.savefig(os.path.join(self.fldr, 'InterCurrentACF_' + self.job_id + '.png'))
            if show:
                fig.show()
        else:
            fig, ax = plt.subplots(1, 1)
            for i, sp_name in enumerate(self.species_names):
                Z = self.dataframe["{} Total Velocity ACF".format(sp_name)]
                ax.plot(self.dataframe["Time"] * self.wp,
                        Z / Z[0], label=r'$Z_{' + sp_name + '} (t)$')
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right')
            ax.set_ylabel(r'$Z(t)$')
            ax.set_xlabel(r'$\omega_p t$')
            ax.set_xscale('log')
            ax.set_ylim(-0.2, 1.2)
            fig.tight_layout()
            fig.savefig(os.path.join(self.fldr, 'TotalVelocityACF_' + self.job_id + '.png'))
            if show:
                fig.show()


class VelocityMoments:
    """
    Moments of the velocity distributions defined as

    .. math::
        \\langle v^{\alpha} \\rangle = \\int_{-\\infty}^{\\infty} d v \, f(v) v^{2 \alpha}.


    Parameters
    ----------
    params: object
        Simulation's parameters.

    Attributes
    ----------
    dump_dir: str
        Directory containing simulation's dumps.

    dump_step : int
        Dump step frequency.

    filename_csv: str
        Filename in which to store the Pandas dataframe.

    fldr: str
        Job's directory.

    fname_app: str
        Appendix of file names.

    no_bins: int
        Number of bins used to calculate the velocity distribution.

    no_dumps: int
        Number of simulation's dumps to compute.

    plots_dir: str
        Directory in which to store Hermite coefficients plots.

    a_ws : float
        Wigner-Seitz radius.

    wp : float
        Total plasma frequency.

    kB : float
        Boltzmann constant.

    dt : float
        Timestep magnitude.

    no_species : int
        Number of species.

    species_np: array
        Array of integers with the number of particles for each species.

    species_names : list
        Names of particle species.

    tot_no_ptcls : int
        Total number of particles.

    species_plots_dirs : list, str
        Directory for each species where to save Hermite coefficients plots.

    units: str
        System of units used in the simulation. mks or cgs.

    max_no_moment: int
        Maximum number of moments = :math:`\alpha`. Default = 3.

    """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.dataframe = None
        if not hasattr(params.PostProcessing, 'mom_nbins'):
            # choose the number of bins as 5% of the number of particles
            self.no_bins = int(0.05 * params.total_num_ptcls)
        else:
            self.no_bins = params.PostProcessing.mom_nbins
        self.dump_dir = params.control.dump_dir
        self.no_dumps = len(os.listdir(self.dump_dir))
        #
        self.fldr = os.path.join(params.control.checkpoint_dir, "MomentRatios_Data")
        if not os.path.exists(self.fldr):
            os.mkdir(self.fldr)
        self.plots_dir = os.path.join(self.fldr, 'Plots')
        self.job_id = params.control.fname_app
        self.filename_csv = os.path.join(self.fldr, "VelocityMoments_" + self.job_id + '.csv')
        #
        self.dump_step = params.control.dump_step
        self.no_species = len(params.species)
        self.tot_no_ptcls = params.total_num_ptcls
        self.no_dim = params.dimensions
        self.units = params.control.units
        self.no_steps = params.control.Nsteps
        self.a_ws = params.aws
        self.wp = params.wp
        self.species_np = np.zeros(self.no_species)  # Number of particles of each species
        self.species_names = []
        self.dt = params.control.dt
        self.max_no_moment = 3
        self.species_plots_dirs = None
        self.units = params.control.units
        for i, sp in enumerate(params.species):
            self.species_np[i] = int(sp.num)
            self.species_names.append(sp.name)

    def compute(self):
        """
        Calculate the moments of the velocity distributions and save them to a pandas dataframes and csv.
        """
        vscale = 1. / (self.a_ws * self.wp)
        vel = np.zeros((self.no_dumps, self.tot_no_ptcls, 3))

        time = np.zeros(self.no_dumps)
        for it in range(self.no_dumps):
            dump = int(it * self.dump_step)
            datap = load_from_restart(self.dump_dir, dump)
            vel[it, :, 0] = datap["vel"][:, 0] * vscale
            vel[it, :, 1] = datap["vel"][:, 1] * vscale
            vel[it, :, 2] = datap["vel"][:, 2] * vscale
            time[it] = datap["time"]

        data = {"Time": time}
        self.dataframe = pd.DataFrame(data)
        print("Calculating velocity moments ...")
        moments = calc_moments(vel, self.no_bins, self.species_np)

        print("Calculating ratios ...")
        ratios = calc_moment_ratios(moments, self.species_np, self.no_dumps)
        # Save the dataframe
        for i, sp in enumerate(self.species_names):
            self.dataframe["{} vx 2nd moment".format(sp)] = moments[:, int(9 * i)]
            self.dataframe["{} vx 4th moment".format(sp)] = moments[:, int(9 * i) + 1]
            self.dataframe["{} vx 6th moment".format(sp)] = moments[:, int(9 * i) + 2]

            self.dataframe["{} vy 2nd moment".format(sp)] = moments[:, int(9 * i) + 3]
            self.dataframe["{} vy 4th moment".format(sp)] = moments[:, int(9 * i) + 4]
            self.dataframe["{} vy 6th moment".format(sp)] = moments[:, int(9 * i) + 5]

            self.dataframe["{} vz 2nd moment".format(sp)] = moments[:, int(9 * i) + 6]
            self.dataframe["{} vz 4th moment".format(sp)] = moments[:, int(9 * i) + 7]
            self.dataframe["{} vz 6th moment".format(sp)] = moments[:, int(9 * i) + 8]

            self.dataframe["{} 4-2 moment ratio".format(sp)] = ratios[i, 0, :]
            self.dataframe["{} 6-2 moment ratio".format(sp)] = ratios[i, 1, :]

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')

    def parse(self):
        """
        Grab the pandas dataframe from the saved csv file. If file does not exist call ``compute``.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            print("\nFile {} not found!".format(self.filename_csv))
            print("\nComputing Moments now ...")
            self.compute()

    def plot_ratios(self, show=False):
        """
        Plot the moment ratios and save the figure.

        Parameters
        ----------
        show : bool
            Flag for displaying the figure.
        """
        self.parse()

        if not os.path.exists(self.plots_dir):
            os.mkdir(self.plots_dir)

        if self.no_species > 1:
            self.species_plots_dirs = []
            for i, name in enumerate(self.species_names):
                new_dir = os.path.join(self.plots_dir, "{}".format(name))
                self.species_plots_dirs.append(new_dir)
                if not os.path.exists(new_dir):
                    os.mkdir(os.path.join(self.plots_dir, "{}".format(name)))
        else:
            self.species_plots_dirs = [self.plots_dir]

        for sp, sp_name in enumerate(self.species_names):
            fig, ax = plt.subplots(1, 1)
            xmul, ymul, xprefix, yprefix, xlbl, ylbl = plot_labels(self.dataframe["Time"],
                                                                   np.array([1]), 'Time', 'none', self.units)
            ax.plot(self.dataframe["Time"] * xmul,
                    self.dataframe["{} 4-2 moment ratio".format(sp_name)], label=r"4/2 ratio")
            ax.plot(self.dataframe["Time"] * xmul,
                    self.dataframe["{} 6-2 moment ratio".format(sp_name)], label=r"6/2 ratio")
            ax.axhline(1.0, ls='--', c='k', label='Equilibrium')
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right')
            #
            ax.set_xscale('log')
            # ax.set_yscale('log')
            ax.set_xlabel(r'$t$' + xlbl)
            #
            ax.set_title("Moments ratios of {}".format(sp_name))
            fig.savefig(os.path.join(self.species_plots_dirs[sp], "MomentRatios_" + self.job_id + '.png'))
            if show:
                fig.show()
            else:
                # this is useful because it will have too many figures open.
                plt.close(fig)


class XYZWriter:
    """
    Write the XYZ file for OVITO visualization.

    Parameters
    ----------
    params: object
        Simulation's parameters.

    Attributes
    ----------
    a_ws : float
        Wigner-Seitz radius. Used for rescaling.

    dump_skip : int
        Dump step interval.

    dump_dir : str
        Directory containing Sarkas dumps.

    dump_step : int
        Dump step frequency.

    filename: str
        Name of output files.

    fldr : str
        Folder containing dumps.

    no_dumps : int
        Number of dumps.

    tot_no_ptcls : int
        Total number of particles.

    wp : float
        Plasma frequency used for rescaling.
    """

    def __init__(self, params):
        """
        Initialize the attributes from simulation's parameters.

        Parameters
        ----------
        params: S_params class
            Simulation's parameters.
        """
        self.fldr = params.control.checkpoint_dir
        self.dump_dir = params.control.dump_dir
        self.filename = os.path.join(self.fldr, "pva_" + params.control.fname_app + '.xyz')
        self.dump_step = params.control.dump_step
        self.no_dumps = len(os.listdir(params.control.dump_dir))
        self.dump_skip = 1
        self.tot_no_ptcls = params.total_num_ptcls
        self.a_ws = params.aws
        self.wp = params.wp
        self.verbose = params.control.verbose

    def save(self, dump_skip=1):
        """
        Save the XYZ file by reading Sarkas dumps.

        Parameters
        ----------
        dump_skip : int
            Interval of dumps to skip. Default = 1

        """

        self.dump_skip = dump_skip
        f_xyz = open(self.filename, "w+")

        # Rescale constants. This is needed since OVITO has a small number limit.
        pscale = 1.0 / self.a_ws
        vscale = 1.0 / (self.a_ws * self.wp)
        ascale = 1.0 / (self.a_ws * self.wp ** 2)

        for it in tqdm(range(int(self.no_dumps / self.dump_skip)), disable=not self.verbose):
            dump = int(it * self.dump_step * self.dump_skip)

            data = load_from_restart(self.dump_dir, dump)

            f_xyz.writelines("{0:d}\n".format(self.tot_no_ptcls))
            f_xyz.writelines("name x y z vx vy vz ax ay az\n")
            np.savetxt(f_xyz,
                       np.c_[data["species_name"], data["pos"] * pscale, data["vel"] * vscale, data["acc"] * ascale],
                       fmt="%s %.6e %.6e %.6e %.6e %.6e %.6e %.6e %.6e %.6e")

        f_xyz.close()


@njit
def autocorrelationfunction(At):
    """
    Calculate the autocorrelation function of the array input.

    .. math::
        A(\\tau) =  \sum_j^D \sum_i^T A_j(t_i)A_j(t_i + \\tau)

    where :math:`D` is the number of dimensions and :math:`T` is the total length
    of the simulation.

    Parameters
    ----------
    At : ndarray
        Observable to autocorrelate. Shape=(``no_dim``, ``no_steps``).

    Returns
    -------
    ACF : array
        Autocorrelation function of ``At``.
    """
    no_steps = At.shape[1]
    no_dim = At.shape[0]

    ACF = np.zeros(no_steps)
    Norm_counter = np.zeros(no_steps)

    for it in range(no_steps):
        for dim in range(no_dim):
            ACF[: no_steps - it] += At[dim, it] * At[dim, it:no_steps]
        Norm_counter[: no_steps - it] += 1.0

    return ACF / Norm_counter


@njit
def autocorrelationfunction_1D(At):
    """
    Calculate the autocorrelation function of the input.

    .. math::
        A(\\tau) =  \sum_i^T A(t_i)A(t_i + \\tau)

    where :math:`T` is the total length of the simulation.

    Parameters
    ----------
    At : array
        Array to autocorrelate. Shape=(``no_steps``).

    Returns
    -------
    ACF : array
        Autocorrelation function of ``At``.
    """
    no_steps = At.shape[0]
    ACF = np.zeros(no_steps)
    Norm_counter = np.zeros(no_steps)

    for it in range(no_steps):
        ACF[: no_steps - it] += At[it] * At[it:no_steps]
        Norm_counter[: no_steps - it] += 1.0

    return ACF / Norm_counter


@njit
def calc_Sk(nkt, ka_list, ka_counts, species_np, no_dumps):
    """
    Calculate :math:`S_{ij}(k)` at each saved timestep.

    Parameters
    ----------
    nkt : ndarray, cmplx
        Density fluctuations of all species. Shape = ( ``no_species``, ``no_dumps``, ``no_ka_values``)

    ka_list :
        List of :math:`k` indices in each direction with corresponding magnitude and index of ``ka_counts``.
        Shape=(`no_ka_values`, 5)

    ka_counts : array
        Number of times each :math:`k` magnitude appears.

    species_np : array
        Array with number of particles of each species.

    no_dumps : int
        Number of dumps.

    Returns
    -------

    Sk_all : ndarray
        Array containing :math:`S_{ij}(k)`. Shape=(``no_Sk``, ``no_ka_values``, ``no_dumps``)

    """

    no_sk = int(len(species_np) * (len(species_np) + 1) / 2)
    Sk_all = np.zeros((no_sk, len(ka_counts), no_dumps))

    pair_indx = 0
    for ip, si in enumerate(species_np):
        for jp in range(ip, len(species_np)):
            sj = species_np[jp]
            for it in range(no_dumps):
                for ik, ka in enumerate(ka_list):
                    indx = int(ka[-1])
                    nk_i = nkt[ip, it, ik]
                    nk_j = nkt[jp, it, ik]
                    Sk_all[pair_indx, indx, it] += np.real(np.conj(nk_i) * nk_j) / (ka_counts[indx] * np.sqrt(si * sj))
            pair_indx += 1

    return Sk_all


def calc_Skw(nkt, ka_list, ka_counts, species_np, no_dumps, dt, dump_step):
    """
    Calculate the Fourier transform of the correlation function of ``nkt``.

    Parameters
    ----------
    nkt : nkarray, complex
        Particles' density or velocity fluctuations.
        Shape = ( ``no_species``, ``no_k_list``, ``no_dumps``)

    ka_list : list
        List of :math:`k` indices in each direction with corresponding magnitude and index of ``ka_counts``.
        Shape=(`no_ka_values`, 5)

    ka_counts : array
        Number of times each :math:`k` magnitude appears.

    species_np : array
        Array with one element giving number of particles.

    no_dumps : int
        Number of dumps.

    Returns
    -------
    Skw : ndarray
        DSF/CCF of each species and pair of species.
        Shape = (``no_skw``, ``no_ka_values``, ``no_dumps``)
    """

    norm = dt / np.sqrt(no_dumps * dt * dump_step)
    no_skw = int(len(species_np) * (len(species_np) + 1) / 2)
    Skw = np.empty((no_skw, len(ka_counts), no_dumps))

    pair_indx = 0
    for ip, si in enumerate(species_np):
        for jp in range(ip, len(species_np)):
            sj = species_np[jp]
            for ik, ka in enumerate(ka_list):
                indx = int(ka[-1])
                nkw_i = np.fft.fft(nkt[ip, :, ik]) * norm
                nkw_j = np.fft.fft(nkt[jp, :, ik]) * norm
                Skw[pair_indx, indx, :] += np.real(np.conj(nkw_i) * nkw_j) / (ka_counts[indx] * np.sqrt(si * sj))
            pair_indx += 1
    return Skw


@njit
def calc_elec_current(vel, sp_charge, sp_num):
    """
    Calculate the total electric current and electric current of each species.

    Parameters
    ----------
    vel: array
        Particles' velocities.

    sp_charge: array
        Charge of each species.

    sp_num: array
        Number of particles of each species.

    Returns
    -------
    Js : ndarray
        Electric current of each species. Shape = (``no_species``, ``no_dim``, ``no_dumps``)

    Jtot : ndarray
        Total electric current. Shape = (``no_dim``, ``no_dumps``)
    """
    num_species = len(sp_num)
    no_dumps = vel.shape[0]

    Js = np.zeros((num_species, 3, no_dumps))
    Jtot = np.zeros((3, no_dumps))

    for it in range(no_dumps):
        sp_start = 0
        for s in range(num_species):
            sp_end = sp_start + sp_num[s]
            # Calculate the current of each species
            Js[s, :, it] = sp_charge[s] * np.sum(vel[it, :, sp_start:sp_end], axis=1)
            Jtot[:, it] += Js[s, :, it]

            sp_start = sp_end

    return Js, Jtot


@njit
def calc_moment_ratios(moments, species_np, no_dumps):
    """
    Take the ratio of the velocity moments.

    Parameters
    ----------
    moments: ndarray
        Velocity moments of each species per direction at each time step.

    no_dumps: int
        Number of saved timesteps.

    species_np: array
        Number of particles of each species.

    Returns
    -------
    ratios: ndarray
        Ratios of high order velocity moments with respoect the 2nd moment.
        Shape=(``no_species``,2, ``no_dumps``)
    """

    no_ratios = 2
    ratios = np.zeros((len(species_np), no_ratios, no_dumps))

    sp_start = 0
    for sp, nsp in enumerate(species_np):
        sp_end = sp_start + nsp

        vx2_mom = moments[:, int(9 * sp)]
        vx4_mom = moments[:, int(9 * sp) + 1]
        vx6_mom = moments[:, int(9 * sp) + 2]

        vy2_mom = moments[:, int(9 * sp) + 3]
        vy4_mom = moments[:, int(9 * sp) + 4]
        vy6_mom = moments[:, int(9 * sp) + 5]

        vz2_mom = moments[:, int(9 * sp) + 6]
        vz4_mom = moments[:, int(9 * sp) + 7]
        vz6_mom = moments[:, int(9 * sp) + 8]

        ratios[sp, 0, :] = (vx4_mom / vx2_mom ** 2) * (vy4_mom / vy2_mom ** 2) * (vz4_mom / vz2_mom ** 2) / 27.0
        ratios[sp, 1, :] = (vx6_mom / vx2_mom ** 3) * (vy6_mom / vy2_mom ** 3) * (vz6_mom / vz2_mom ** 3) / 15.0 ** 3

        sp_start = sp_end

    print('Done')
    return ratios


def calc_moments(vel, nbins, species_np):
    """
    Calculate the even moments of the velocity distributions.

    Parameters
    ----------
    vel: ndarray
        Particles' velocity at each time step.

    nbins: int
        Number of bins to be used for the distribution.

    species_np: array
        Number of particles of each species.

    Returns
    -------
    moments: ndarray
        2nd, 4th, 8th moment of the velocity distributions.
        Shape=( ``no_dumps``, ``9 * len(species_np)``)
    """

    no_dumps = vel.shape[0]
    moments = np.empty((no_dumps, int(9 * len(species_np))))

    for it in range(no_dumps):
        sp_start = 0
        for sp, nsp in enumerate(species_np):
            sp_end = sp_start + int(nsp)

            xdist, xbins = np.histogram(vel[it, sp_start:sp_end, 0], bins=nbins, density=True)
            ydist, ybins = np.histogram(vel[it, sp_start:sp_end, 1], bins=nbins, density=True)
            zdist, zbins = np.histogram(vel[it, sp_start:sp_end, 2], bins=nbins, density=True)

            vx = (xbins[:-1] + xbins[1:]) / 2.
            vy = (ybins[:-1] + ybins[1:]) / 2.
            vz = (zbins[:-1] + zbins[1:]) / 2.

            moments[it, int(9 * sp)] = np.sum(vx ** 2 * xdist) * abs(vx[1] - vx[0])
            moments[it, int(9 * sp) + 1] = np.sum(vx ** 4 * xdist) * abs(vx[1] - vx[0])
            moments[it, int(9 * sp) + 2] = np.sum(vx ** 6 * xdist) * abs(vx[1] - vx[0])

            moments[it, int(9 * sp) + 3] = np.sum(vy ** 2 * ydist) * abs(vy[1] - vy[0])
            moments[it, int(9 * sp) + 4] = np.sum(vy ** 4 * ydist) * abs(vy[1] - vy[0])
            moments[it, int(9 * sp) + 5] = np.sum(vy ** 6 * ydist) * abs(vy[1] - vy[0])

            moments[it, int(9 * sp) + 6] = np.sum(vz ** 2 * zdist) * abs(vz[1] - vz[0])
            moments[it, int(9 * sp) + 7] = np.sum(vz ** 4 * zdist) * abs(vz[1] - vz[0])
            moments[it, int(9 * sp) + 8] = np.sum(vz ** 6 * zdist) * abs(vz[1] - vz[0])

            sp_start = sp_end

    return moments


@njit
def calc_nk(pos_data, k_list):
    """
    Calculate the instantaneous microscopic density :math:`n(k)` defined as

    .. math::
        n_{A} ( k ) = \sum_i^{N_A} \exp [ -i \mathbf k \cdot \mathbf r_{i} ]

    Parameters
    ----------
    pos_data : ndarray
        Particles' position scaled by the box lengths.
        Shape = ( ``no_dumps``, ``no_dim``, ``tot_no_ptcls``)

    k_list : list
        List of :math:`k` indices in each direction with corresponding magnitude and index of ``ka_counts``.
        Shape=(``no_ka_values``, 5)

    Returns
    -------
    nk : array
        Array containing :math:`n(k)`.
    """

    nk = np.zeros(len(k_list), dtype=np.complex128)

    for ik, k_vec in enumerate(k_list):
        kr_i = 2.0 * np.pi * (k_vec[0] * pos_data[:, 0] + k_vec[1] * pos_data[:, 1] + k_vec[2] * pos_data[:, 2])
        nk[ik] = np.sum(np.exp(-1j * kr_i))

    return nk


def calc_nkt(fldr, no_dumps, dump_step, species_np, k_list):
    """
    Calculate density fluctuations :math:`n(k,t)` of all species.

    .. math::
        n_{A} ( k, t ) = \sum_i^{N_A} \exp [ -i \mathbf k \cdot \mathbf r_{i}(t) ]

    where :math:`N_A` is the number of particles of species :math:`A`.

    Parameters
    ----------
    fldr : str
        Name of folder containing particles data.

    no_dumps : int
        Number of saved timesteps.

    dump_step : int
        Timestep interval saving.

    species_np : array
        Number of particles of each species.

    k_list : list
        List of :math: `k` vectors.

    Return
    ------
    nkt : ndarray, complex
        Density fluctuations.  Shape = ( ``no_species``, ``no_dumps``, ``no_ka_values``)
    """
    # Read particles' position for all times
    print("Calculating n(k,t).")
    nkt = np.zeros((len(species_np), no_dumps, len(k_list)), dtype=np.complex128)
    for it in range(no_dumps):
        dump = int(it * dump_step)
        data = load_from_restart(fldr, dump)
        pos = data["pos"]
        sp_start = 0
        for i, sp in enumerate(species_np):
            sp_end = sp_start + sp
            nkt[i, it, :] = calc_nk(pos[sp_start:sp_end, :], k_list)
            sp_start = sp_end

    return nkt


@njit
def calc_pressure_tensor(pos, vel, acc, species_mass, species_np, box_volume):
    """
    Calculate the pressure tensor.

    Parameters
    ----------
    pos : ndarray
        Particles' positions.

    vel : ndarray
        Particles' velocities.

    acc : ndarray
        Particles' accelerations.

    species_mass : array
        Mass of each species.

    species_np : array
        Number of particles of each species.

    box_volume : float
        Volume of simulation's box.

    Returns
    -------
    pressure : float
        Scalar Pressure i.e. trace of the pressure tensor

    pressure_tensor : ndarray
        Pressure tensor. Shape(``no_dim``,``no_dim``)

    """
    sp_start = 0
    # Rescale vel and acc of each particle by their individual mass
    for sp in range(len(species_np)):
        sp_end = sp_start + species_np[sp]
        vel[:, sp_start: sp_end] *= np.sqrt(species_mass[sp])
        acc[:, sp_start: sp_end] *= species_mass[sp]  # force
        sp_start = sp_end

    pressure_tensor = (vel @ np.transpose(vel) + pos @ np.transpose(acc)) / box_volume
    pressure = np.trace(pressure_tensor) / 3.0

    return pressure, pressure_tensor


@njit
def calc_statistical_efficiency(observable, run_avg, run_std, max_no_divisions, no_dumps):
    """
    Todo:

    Parameters
    ----------
    observable
    run_avg
    run_std
    max_no_divisions
    no_dumps

    Returns
    -------

    """
    tau_blk = np.zeros(max_no_divisions)
    sigma2_blk = np.zeros(max_no_divisions)
    statistical_efficiency = np.zeros(max_no_divisions)
    for i in range(2, max_no_divisions):
        tau_blk[i] = int(no_dumps / i)
        for j in range(i):
            t_start = int(j * tau_blk[i])
            t_end = int((j + 1) * tau_blk[i])
            blk_avg = observable[t_start:t_end].mean()
            sigma2_blk[i] += (blk_avg - run_avg) ** 2
        sigma2_blk[i] /= (i - 1)
        statistical_efficiency[i] = tau_blk[i] * sigma2_blk[i] / run_std ** 2

    return tau_blk, sigma2_blk, statistical_efficiency


@njit
def calc_vacf(vel, sp_num, sp_mass, time_averaging, it_skip):
    """
    Calculate the velocity autocorrelation function of each species and in each direction.

    Parameters
    ----------
    time_averaging: bool
        Flag for time averaging.

    it_skip: int
        Timestep interval for time averaging.

    vel : ndarray
        Particles' velocities.

    sp_num: array
        Number of particles of each species.

    Returns
    -------
    vacf_x: ndarray
        x-velocity autocorrelation function

    vacf_y: ndarray
        y-velocity autocorrelation function

    vacf_z: ndarray
        z-velocity autocorrelation function

    vacf_tot: ndarray
        total velocity autocorrelation function
    """

    no_dim = vel.shape[0]
    no_dumps = vel.shape[2]
    no_species = len(sp_num)
    no_vacf = int(no_species * (no_species + 1) / 2)
    com_vel = np.zeros((no_species, 3, no_dumps))

    tot_mass_dens = np.sum(sp_num * sp_mass)

    sp_start = 0
    for i in range(no_species):
        sp_end = sp_start + sp_num[i]
        com_vel[i, :, :] = sp_mass[i] * np.sum(vel[:, sp_start: sp_end, :], axis=1) / tot_mass_dens
        sp_start = sp_end

    tot_com_vel = np.sum(com_vel, axis=0)

    jc_acf = np.zeros((no_vacf, no_dim + 1, no_dumps))

    if time_averaging:
        indx = 0
        for i in range(no_species):
            sp1_flux = sp_mass[i] * float(sp_num[i]) * (com_vel[i] - tot_com_vel)
            for j in range(i, no_species):
                sp2_flux = sp_mass[j] * float(sp_num[j]) * (com_vel[j] - tot_com_vel)
                for d in range(no_dim):
                    norm_counter = np.zeros(no_dumps)
                    temp = np.zeros(no_dumps)
                    for it in range(0, no_dumps, it_skip):
                        temp[:no_dumps - it] += correlationfunction_1D(sp1_flux[d, it:], sp2_flux[d, it:])
                        norm_counter[:(no_dumps - it)] += 1.0
                    jc_acf[indx, d, :] = temp / norm_counter

                norm_counter = np.zeros(no_dumps)
                temp = np.zeros(no_dumps)
                for it in range(0, no_dumps, it_skip):
                    temp[: no_dumps - it] += correlationfunction(sp1_flux[:, it:], sp2_flux[:, it:])
                    norm_counter[:(no_dumps - it)] += 1.0
                jc_acf[indx, no_dim, :] = temp / norm_counter
                indx += 1

    else:
        indx = 0
        for i in range(no_species):
            sp1_flux = sp_mass[i] * float(sp_num[i]) * (com_vel[i] - tot_com_vel)
            for j in range(i, no_species):
                sp2_flux = sp_mass[j] * float(sp_num[j]) * (com_vel[j] - tot_com_vel)
                for d in range(no_dim):
                    jc_acf[indx, d, :] = correlationfunction_1D(sp1_flux[d, :], sp2_flux[d, :])

                jc_acf[indx, d + 1, :] = correlationfunction(sp1_flux, sp2_flux)
                indx += 1

    return jc_acf


@njit
def calc_vacf_single(vel, sp_num, sp_mass, time_averaging, it_skip=100):
    """
    Calculate the velocity autocorrelation function of each species and in each direction.

    Parameters
    ----------
    time_averaging: bool
        Flag for time averaging.

    it_skip: int
        Timestep interval for time averaging.

    vel : ndarray
        Particles' velocities.

    sp_num: array
        Number of particles of each species.

    Returns
    -------
    vacf: array
        Velocity autocorrelation functions.

    """
    no_dim = vel.shape[0]
    no_dumps = vel.shape[2]

    vacf = np.zeros((1, no_dim + 1, no_dumps))

    if time_averaging:
        for d in range(no_dim):
            vacf_temp = np.zeros(no_dumps)
            norm_counter = np.zeros(no_dumps)

            for ptcl in range(sp_num[0]):
                for it in range(0, no_dumps, it_skip):
                    vacf_temp[: no_dumps - it] += autocorrelationfunction_1D(vel[d, ptcl, it:])
                    norm_counter[: no_dumps - it] += 1.0

            vacf[0, d, :] = vacf_temp / norm_counter

        vacf_temp = np.zeros(no_dumps)
        norm_counter = np.zeros(no_dumps)
        for ptcl in range(sp_num[0]):
            for it in range(0, no_dumps, it_skip):
                vacf_temp[: no_dumps - it] += autocorrelationfunction(vel[:, ptcl, it:])
                norm_counter[: no_dumps - it] += 1.0

        vacf[0, -1, :] = vacf_temp / norm_counter
    else:
        # Calculate species mass density flux
        for i in range(3):
            vacf_temp = np.zeros(no_dumps)
            for ptcl in range(sp_num[0]):
                vacf += autocorrelationfunction_1D(vel[i, ptcl, :])
            vacf[0, i, :] = vacf_temp / sp_num[0]

        vacf_temp = np.zeros(no_dumps)
        for ptcl in range(sp_num[0]):
            vacf_temp += autocorrelationfunction(vel[:, ptcl, :])

        vacf[0, -1, :] = vacf_temp / sp_num[0]

    return vacf


@njit
def calc_vk(pos_data, vel_data, k_list):
    """
    Calculate the instantaneous longitudinal and transverse velocity fluctuations.

    Parameters
    ----------
    pos_data : ndarray
        Particles' position. Shape = ( ``no_dumps``, 3, ``tot_no_ptcls``)

    vel_data : ndarray
        Particles' velocities. Shape = ( ``no_dumps``, 3, ``tot_no_ptcls``)

    k_list : list
        List of :math:`k` indices in each direction with corresponding magnitude and index of ``ka_counts``.
        Shape=(``no_ka_values``, 5)

    Returns
    -------
    vkt : ndarray
        Array containing longitudinal velocity fluctuations.

    vkt_i : ndarray
        Array containing transverse velocity fluctuations in the :math:`x` direction.

    vkt_j : ndarray
        Array containing transverse velocity fluctuations in the :math:`y` direction.

    vkt_k : ndarray
        Array containing transverse velocity fluctuations in the :math:`z` direction.
    """

    # Longitudinal
    vk = np.zeros(len(k_list), dtype=np.complex128)

    # Transverse
    vk_i = np.zeros(len(k_list), dtype=np.complex128)
    vk_j = np.zeros(len(k_list), dtype=np.complex128)
    vk_k = np.zeros(len(k_list), dtype=np.complex128)

    for ik, k_vec in enumerate(k_list):
        kr_i = 2.0 * np.pi * (k_vec[0] * pos_data[:, 0] + k_vec[1] * pos_data[:, 1] + k_vec[2] * pos_data[:, 2])
        k_dot_v = 2.0 * np.pi * (k_vec[0] * vel_data[:, 0] + k_vec[1] * vel_data[:, 1] + k_vec[2] * vel_data[:, 2])
        vk[ik] = np.sum(k_dot_v * np.exp(-1j * kr_i))

        k_cross_v_i = 2.0 * np.pi * (k_vec[1] * vel_data[:, 2] - k_vec[2] * vel_data[:, 1])
        k_cross_v_j = -2.0 * np.pi * (k_vec[0] * vel_data[:, 2] - k_vec[2] * vel_data[:, 0])
        k_cross_v_k = 2.0 * np.pi * (k_vec[0] * vel_data[:, 1] - k_vec[1] * vel_data[:, 0])
        vk_i[ik] = np.sum(k_cross_v_i * np.exp(-1j * kr_i))
        vk_j[ik] = np.sum(k_cross_v_j * np.exp(-1j * kr_i))
        vk_k[ik] = np.sum(k_cross_v_k * np.exp(-1j * kr_i))

    return vk, vk_i, vk_j, vk_k


def calc_vkt(fldr, no_dumps, dump_step, species_np, k_list):
    """
    Calculate the longitudinal and transverse velocities fluctuations of all species.
    Longitudinal

    .. math::
        \lambda_A(\mathbf{k}, t) = \sum_i^{N_A} \mathbf{k} \cdot \mathbf{v}_{i}(t) \exp [ - i \mathbf{k} \cdot \mathbf{r}_{i}(t) ]

    Transverse

    .. math::
        \\tau_A(\mathbf{k}, t) = \sum_i^{N_A} \mathbf{k} \\times \mathbf{v}_{i}(t) \exp [ - i \mathbf{k} \cdot \mathbf{r}_{i}(t) ]

    where :math:`N_A` is the number of particles of species :math:`A`.

    Parameters
    ----------
    fldr : str
        Name of folder containing particles data.

    no_dumps : int
        Number of saved timesteps.

    dump_step : int
        Timestep interval saving.

    species_np : array
        Number of particles of each species.

    k_list : list
        List of :math: `k` vectors.

    Returns
    -------
    vkt : ndarray, complex
        Longitudinal velocity fluctuations.
        Shape = ( ``no_species``, ``no_dumps``, ``no_ka_values``)

    vkt_perp_i : ndarray, complex
        Transverse velocity fluctuations along the :math:`x` axis.
        Shape = ( ``no_species``, ``no_dumps``, ``no_ka_values``)

    vkt_perp_j : ndarray, complex
        Transverse velocity fluctuations along the :math:`y` axis.
        Shape = ( ``no_species``, ``no_dumps``, ``no_ka_values``)

    vkt_perp_k : ndarray, complex
        Transverse velocity fluctuations along the :math:`z` axis.
        Shape = ( ``no_species``, ``no_dumps``, ``no_ka_values``)

    """
    # Read particles' position for all times
    print("Calculating longitudinal and transverse microscopic velocity fluctuations v(k,t).")
    vkt_par = np.zeros((len(species_np), no_dumps, len(k_list)), dtype=np.complex128)
    vkt_perp_i = np.zeros((len(species_np), no_dumps, len(k_list)), dtype=np.complex128)
    vkt_perp_j = np.zeros((len(species_np), no_dumps, len(k_list)), dtype=np.complex128)
    vkt_perp_k = np.zeros((len(species_np), no_dumps, len(k_list)), dtype=np.complex128)
    for it in range(no_dumps):
        dump = int(it * dump_step)
        data = load_from_restart(fldr, dump)
        pos = data["pos"]
        vel = data["vel"]
        sp_start = 0
        for i, sp in enumerate(species_np):
            sp_end = sp_start + sp
            vkt_par[i, it, :], vkt_perp_i[i, it, :], vkt_perp_j[i, it, :], vkt_perp_k[i, it, :] = calc_vk(
                pos[sp_start:sp_end, :], vel[sp_start:sp_end], k_list)
            sp_start = sp_end

    return vkt_par, vkt_perp_i, vkt_perp_j, vkt_perp_k


def calculate_herm_coeff(v, distribution, maxpower):
    """
    Calculate Hermite coefficients by integrating the velocity distribution function. That is

    .. math::
        a_i = \int_{-\\infty}^{\infty} dv \, He_i(v)f(v)

    Parameters
    ----------
    v : array
        Range of velocities.

    distribution: array
        Velocity histogram.

    maxpower: int
        Hermite order

    Returns
    -------
    coeff: array
        Coefficients :math:`a_i`

    """
    coeff = np.zeros(maxpower + 1)
    for i in range(maxpower + 1):
        hc = np.zeros(1 + i)
        hc[-1] = 1.0
        Hp = np.polynomial.hermite_e.hermeval(v, hc)
        coeff[i] = np.trapz(distribution * Hp, x=v)

    return coeff


@njit
def correlationfunction(At, Bt):
    """
    Calculate the correlation function :math:`\mathbf{A}(t)` and :math:`\mathbf{B}(t)`

    .. math::
        C_{AB}(\\tau) =  \sum_j^D \sum_i^T A_j(t_i)B_j(t_i + \\tau)

    where :math:`D` (= ``no_dim``) is the number of dimensions and :math:`T` (= ``no_steps``) is the total length
    of the simulation.

    Parameters
    ----------
    At : ndarray
        Observable to correlate. Shape=(``no_dim``, ``no_steps``).

    Bt : ndarray
        Observable to correlate. Shape=(``no_dim``, ``no_steps``).

    Returns
    -------
    CF : array
        Correlation function :math:`C_{AB}(\\tau)`
    """
    no_steps = At.shape[1]
    no_dim = At.shape[0]

    CF = np.zeros(no_steps)
    Norm_counter = np.zeros(no_steps)

    for it in range(no_steps):
        for dim in range(no_dim):
            CF[: no_steps - it] += At[dim, it] * Bt[dim, it:no_steps]
        Norm_counter[: no_steps - it] += 1.0

    return CF / Norm_counter


@njit
def correlationfunction_1D(At, Bt):
    """
    Calculate the correlation function between :math:`A(t)` and :math:`B(t)`

    .. math::
        C_{AB}(\\tau) =  \sum_i^T A(t_i)B(t_i + \\tau)

    where :math:`T` (= ``no_steps``) is the total length of the simulation.

    Parameters
    ----------
    At : array
        Observable to correlate. Shape=(``no_steps``).

    Bt : array
        Observable to correlate. Shape=(``no_steps``).

    Returns
    -------
    CF : array
        Correlation function :math:`C_{AB}(\\tau)`
    """
    no_steps = At.shape[0]
    CF = np.zeros(no_steps)
    Norm_counter = np.zeros(no_steps)

    for it in range(no_steps):
        CF[: no_steps - it] += At[it] * Bt[it:no_steps]
        Norm_counter[: no_steps - it] += 1.0

    return CF / Norm_counter


def kspace_setup(no_ka, box_lengths):
    """
    Calculate all allowed :math:`k` vectors.

    Parameters
    ----------
    no_ka : array
        Number of harmonics in each direction.

    box_lengths : array
        Length of each box's side.

    Returns
    -------
    k_arr : list
        List of all possible :math:`k` vectors with their corresponding magnitudes and indexes.

    k_counts : array
        Number of occurrences of each :math:`k` magnitude.

    k_unique : array
        Magnitude of each allowed :math:`k` vector.
    """
    # Obtain all possible permutations of the wave number arrays
    k_arr = [np.array([i / box_lengths[0], j / box_lengths[1], k / box_lengths[2]]) for i in range(no_ka[0])
             for j in range(no_ka[1])
             for k in range(no_ka[2])]

    # Compute wave number magnitude - don't use |k| (skipping first entry in k_arr)
    k_mag = np.sqrt(np.sum(np.array(k_arr) ** 2, axis=1)[..., None])

    # Add magnitude to wave number array
    k_arr = np.concatenate((k_arr, k_mag), 1)

    # Sort from lowest to highest magnitude
    ind = np.argsort(k_arr[:, -1])
    k_arr = k_arr[ind]

    # Count how many times a |k| value appears
    k_unique, k_counts = np.unique(k_arr[1:, -1], return_counts=True)

    # Generate a 1D array containing index to be used in S array
    k_index = np.repeat(range(len(k_counts)), k_counts)[..., None]

    # Add index to k_array
    k_arr = np.concatenate((k_arr[1:, :], k_index), 1)
    return k_arr, k_counts, k_unique


def load_from_restart(fldr, it):
    """
    Load particles' data from dumps.

    Parameters
    ----------
    fldr : str
        Folder containing dumps.

    it : int
        Timestep to load.

    Returns
    -------
    data : dict
        Particles' data.
    """

    file_name = os.path.join(fldr, "S_checkpoint_" + str(it) + ".npz")
    data = np.load(file_name, allow_pickle=True)
    return data


def plot_labels(xdata, ydata, xlbl, ylbl, units):
    """
    Create plot labels with correct units and prefixes.

    Parameters
    ----------
    xdata: array
        X values.

    ydata: array
        Y values.

    xlbl: str
        String of the X quantity.

    ylbl: str
        String of the Y quantity.

    units: str
        'cgs' or 'mks'.

    Returns
    -------
    xmultiplier: float
        Scaling factor for X data.

    ymultiplier: float
        Scaling factor for Y data.

    xprefix: str
        Prefix for X units label

    yprefix: str
         Prefix for Y units label.

    xlabel: str
        X label units.

    ylabel: str
        Y label units.

    """
    if isinstance(xdata, (np.ndarray, pd.core.series.Series)):
        xmax = xdata.max()
    else:
        xmax = xdata

    if isinstance(ydata, (np.ndarray, pd.core.series.Series)):
        ymax = ydata.max()
    else:
        ymax = ydata

    x_str = np.format_float_scientific(xmax)
    y_str = np.format_float_scientific(ymax)

    x_exp = 10.0 ** (float(x_str[x_str.find('e') + 1:]))
    y_exp = 10.0 ** (float(y_str[y_str.find('e') + 1:]))

    # find the prefix
    xprefix = "none"
    xmul = -1.5
    i = 0.1
    while xmul < 0:
        i *= 10.
        for key, value in PREFIXES.items():
            ratio = i * x_exp / value
            if abs(ratio - 1) < 1.0e-6:
                xprefix = key
                xmul = i / value

    # find the prefix
    yprefix = "none"
    ymul = - 1.5
    i = 1.0
    while ymul < 0:
        for key, value in PREFIXES.items():
            ratio = i * y_exp / value
            if abs(ratio - 1) < 1.0e-6:
                yprefix = key
                ymul = i / value
        i *= 10.

    # Find the correct Units
    units_dict = UNITS[1] if units == 'cgs' else UNITS[0]

    if "Energy" in ylbl:
        yname = "Energy"
    else:
        yname = ylbl

    if "Pressure" in ylbl:
        yname = "Pressure"
    else:
        yname = ylbl

    if yname in units_dict:
        ylabel = ' [' + yprefix + units_dict[yname] + ']'
    else:
        ylabel = ''

    if "Energy" in xlbl:
        xname = "Energy"
    else:
        xname = xlbl

    if "Pressure" in xlbl:
        xname = "Pressure"
    else:
        xname = xlbl

    if xname in units_dict:
        xlabel = ' [' + xprefix + units_dict[xname] + ']'
    else:
        xlabel = ''

    return xmul, ymul, xprefix, yprefix, xlabel, ylabel


def read_pickle(params_dir):
    """
    Read Pickle File containing params.

    Parameters
    ----------
    params_dir: str
        Input YAML file of the simulation.

    Returns
    -------
    data : dict
        Params dictionary.

    """

    pickle_file = os.path.join(params_dir, "S_parameters.pickle")

    data = np.load(pickle_file, allow_pickle=True)

    return data