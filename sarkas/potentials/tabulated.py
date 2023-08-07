r"""
Module for handling custom potential of the form given below.

Potential Attributes
********************
The elements of the :attr:`sarkas.potentials.core.Potential.matrix` are:

.. code-block:: python

    pot_matrix[0] = q_iq_je^2/(4 pi eps_0) Force factor between two particles.
    pot_matrix[1] = kappa
    pot_matrix[2] = a
    pot_matrix[3] = b
    pot_matrix[4] = c
    pot_matrix[5] = d
    pot_matrix[6] = a_rs. Short-range cutoff.

"""
from numba import jit
from numba.core.types import float64, UniTuple
from numpy import inf, interp, loadtxt, pi, sqrt, where, zeros
from scipy.integrate import quad


@jit(UniTuple(float64, 2)(float64, float64[:, :]), nopython=True)
def tab_force(r, pot_matrix):
    """
    Numba'd function to calculate the PP force between particles using the Moliere Potential.

    Parameters
    ----------
    r : float
        Particles' distance.

    pot_matrix : numpy.ndarray
        Slice of `sarkas.potentials.Potential.matrix` containing the potential parameters.

    Returns
    -------
    u_r : float
        Potential.

    f_r : float
        Force between two particles.

    """

    # Unpack the parameters
    # r_tab = pot_matrix[0, :]
    # u_tab = pot_matrix[1, :]
    # f_tab = pot_matrix[2, :]
    dr = pot_matrix[0, 0]
    rbin = int(r / dr)
    # The following branchless programming is needed because numba was grabbing the wrong array element when rbin > rc.
    u_r = pot_matrix[1, rbin] * (rbin < pot_matrix.shape[1]) + 0.0
    f_r = pot_matrix[2, rbin] * (rbin < pot_matrix.shape[1]) + 0.0

    return u_r, f_r


def potential_derivatives(r, pot_matrix):
    """Calculate the first and second derivative of the potential.

    Parameters
    ----------
    r_in : float
        Distance between two particles.

    pot_matrix : numpy.ndarray
        It contains potential dependent variables.

    Returns
    -------
    u_r : float, numpy.ndarray
        Potential value.

    dv_dr : float, numpy.ndarray
        First derivative of the potential.

    d2v_dr2 : float, numpy.ndarray
        Second derivative of the potential.

    """

    # Unpack the parameters
    r_tab = pot_matrix[0, :]
    u_tab = pot_matrix[1, :]
    f_tab = pot_matrix[2, :]
    f2_tab = pot_matrix[3, :]

    u_r = interp(r, r_tab, u_tab)
    dv_dr = interp(r, r_tab, -f_tab)
    d2v_dr2 = interp(r, r_tab, f2_tab)

    return u_r, dv_dr, d2v_dr2


def pretty_print_info(potential):
    """
    Print potential specific parameters in a user-friendly way.

    Parameters
    ----------
    potential : :class:`sarkas.potentials.core.Potential`
        Class handling potential form.

    """
    msg = (
        f"screening type : {potential.screening_length_type}\n"
        f"screening length = {potential.screening_length:.6e} {potential.units_dict['length']}\n"
        f"kappa = {potential.a_ws / potential.screening_length:.4f}\n"
        f"Gamma_eff = {potential.coupling_constant:.2f}\n"
    )
    print(msg)


def update_params(potential):
    """
    Assign potential dependent simulation's parameters.

    Parameters
    ----------
    potential : :class:`sarkas.potentials.core.Potential`
        Class handling potential form.

    """
    r, u, f, f2 = loadtxt(potential.tabulated_file, skiprows=1, unpack=True, delimiter=",")
    dr = r[1] - r[2]
    mask = where(r < potential.rc + dr)[0]
    params_len = len(r[mask])

    potential.matrix = zeros((potential.num_species, potential.num_species, 4, params_len))
    beta = 1.0 / (potential.kB * potential.electron_temperature)

    for i, q1 in enumerate(potential.species_charges):
        for j, q2 in enumerate(potential.species_charges):
            potential.matrix[i, j, 0, :] = r[mask]
            potential.matrix[i, j, 1, :] = u[mask]
            potential.matrix[i, j, 2, :] = f[mask]
            potential.matrix[i, j, 3, :] = f2[mask]
    potential.force = tab_force
    # _, f_rc = fit_force(potential.rc, potential.matrix[:, 0, 0])
    # _, f_2a = fit_force(2.0 * potential.a_ws, potential.matrix[:, 0, 0])
    # potential.force_error = f_rc / f_2a
    potential.potential_derivatives = potential_derivatives
    potential.force_error = calc_force_error_quad(potential.a_ws, beta, potential.rc, potential.matrix[0, 0])


def force_error_integrand(r, pot_matrix):
    r"""Auxiliary function to be used in `scipy.integrate.quad` to calculate the integrand.

    Parameters
    ----------
    r_in : float
        Distance between two particles.

    pot_matrix : numpy.ndarray
        Slice of the `sarkas.potentials.core.Potential.matrix` containing the necessary potential parameters.

    Returns
    -------
    _ : float
        Integrand :math:`4\pi r^2 ( d r\phi(r)/dr )^2`

    """

    _, dv_dr, _ = potential_derivatives(r, pot_matrix)

    return 4.0 * pi * r**2 * dv_dr**2


def calc_force_error_quad(a, beta, rc, pot_matrix):
    r"""
    Calculate the force error by integrating the square modulus of the force over the neglected volume.\n
    The force error is calculated from

    .. math::
        \Delta F =  \left [ 4 \pi \int_{r_c}^{\infty} dr \, r^2  \left ( \frac{d\phi(r)}{r} \right )^2 ]^{1/2}

    where :math:`\phi(r)` is only the radial part of the potential, :math:`r_c` is the cutoff radius, and :math:`r` is scaled by the input parameter `a`.\n
    The integral is calculated using `scipy.integrate.quad`. The derivative of the potential is obtained from :meth:`potential_derivatives`.

    Parameters
    ----------
    a : float
        Rescaling length. Usually it is the Wigner-Seitz radius.

    rc : float
        Cutoff radius to be used as the lower limit of the integral. The lower limit is actually `rc /a`.

    pot_matrix: numpy.ndarray
        Slice of the `sarkas.potentials.Potential.matrix` containing the parameters of the potential. It must be a 1D-array.

    Returns
    -------
    f_err: float
        Force error. It is the sqrt root of the integral. It is calculated using `scipy.integrate.quad`  and :func:`potential_derivatives`.

    """

    params = pot_matrix.copy()
    params[0, :] /= a  # a
    params[1, :] *= beta  # a
    params[2, :] *= beta  # a

    r_c = rc / a

    result, _ = quad(force_error_integrand, a=r_c, b=inf, args=(params,))

    f_err = sqrt(result)

    return f_err
