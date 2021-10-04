"""Module of mathematical functions."""

import numpy as np
import numba as nb

TWOPI = 2.0 * np.pi

@nb.njit
def yukawa_green_function(x, alpha, kappa):
    """
    Green's function of Coulomb/Yukawa potential.
    """
    return 4.0 * np.pi * np.exp(-(x ** 2 + kappa ** 2) / (2 * alpha) ** 2) / (kappa ** 2 + x ** 2)


@nb.njit
def betamp(m, p, alpha, kappa):
    """
    Calculate the integral of the Yukawa Green's function
    .. math::

        \beta(p,m) = \int_0^\infty G_k^2 k^{2 (p + m + 2)}.

    See eq.(37) in Dharuman et al. J Chem Phys 146 024112 (2017)
    """
    xa = np.linspace(0.0001, 500, 5000)
    Gk = yukawa_green_function(xa, alpha, kappa)
    return np.trapz(Gk * Gk * xa ** (2 * (m + p + 2)), x=xa)


@nb.njit
def force_error_approx_pppm(kappa, rc, p, h, alpha):
    """
    Calculate the total force error for a given value of ``rc`` and ``alpha``.
    See similar function above.
    """
    # Coefficients from Deserno and Holm J Chem Phys 109 7694 (1998)
    if p == 1:
        Cmp = np.array([2 / 3])
    elif p == 2:
        Cmp = np.array([2 / 45, 8 / 189])
    elif p == 3:
        Cmp = np.array([4 / 495, 2 / 225, 8 / 1485])
    elif p == 4:
        Cmp = np.array([2 / 4725, 16 / 10395, 5528 / 3869775, 32 / 42525])
    elif p == 5:
        Cmp = np.array([4 / 93555, 2764 / 11609325, 8 / 25515, 7234 / 32531625, 350936 / 3206852775])
    elif p == 6:
        Cmp = np.array([2764 / 638512875, 16 / 467775, 7234 / 119282625, 1403744 / 25196700375,
                        1396888 / 40521009375, 2485856 / 152506344375])
    elif p == 7:
        Cmp = np.array([8 / 18243225, 7234 / 1550674125, 701872 / 65511420975, 2793776 / 225759909375,
                        1242928 / 132172165125, 1890912728 / 352985880121875, 21053792 / 8533724574375])

    somma = 0.0
    for m in np.arange(p):
        expp = 2 * (m + p)
        somma += Cmp[m] * (2 / (1 + expp)) * betamp(m, p, alpha, kappa) * (h / 2.) ** expp
    # eq.(36) in Dharuman J Chem Phys 146 024112 (2017)
    pm_force_error = np.sqrt(3.0 * somma) / (2.0 * np.pi)

    # eq.(30) from Dharuman J Chem Phys 146 024112 (2017)
    pp_force_error = 2.0 * np.exp(-(0.5 * kappa / alpha) ** 2 - alpha ** 2 * rc ** 2) / np.sqrt(rc)
    # eq.(42) from Dharuman J Chem Phys 146 024112 (2017)
    Tot_DeltaF = np.sqrt(pm_force_error ** 2 + pp_force_error ** 2)

    return Tot_DeltaF, pp_force_error, pm_force_error


@nb.njit
def force_error_analytic_pp(potential_type,
                            cutoff_length,
                            potential_matrix,
                            rescaling_const):
    """
    Calculate the force error from its analytic formula.

    Parameters
    ----------
    screening: float

    cutoff_length : float, numpy.ndarray

    rescaling_const: float


    Returns
    -------

    """

    if potential_type in ["yukawa", "egs"]:
        force_error = np.sqrt(TWOPI * potential_matrix[1, 0, 0])\
                      * np.exp(- cutoff_length * potential_matrix[1, 0, 0])
    elif potential_type == "moliere":
        # Choose the smallest screening length for force error calculation

        force_error = np.sqrt(TWOPI * potential_matrix[:, 0, 0].min()) \
                      * np.exp(- cutoff_length * potential_matrix[1, 0, 0])

    elif potential_type == 'lj':
        # choose the highest sigma in case of multispecies
        sigma = potential_matrix[1, :, :].max()
        high_pow = potential_matrix[2, 0, 0]
        exponent = 2 * high_pow - 1
        force_error_tmp = high_pow**2 * sigma**(2 * high_pow)/cutoff_length**exponent
        force_error_tmp /= exponent
        force_error = np.sqrt(force_error_tmp)

    # Renormalize
    force_error *= rescaling_const
