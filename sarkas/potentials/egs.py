"""
Module for handling Exact Gradient corrected Screened (EGS) Potential.

Potential
*********

The exact-gradient screened (EGS) potential introduces new parameters that can be easily calculated from initial inputs.
Density gradient corrections to the free energy functional lead to the first parameter, :math:`\\nu`,

.. math::
   \\nu = - \\frac{3\\lambda}{\\pi^{3/2}}  \\frac{4\\pi \\bar{e}^2 \\beta }{\\Lambda_{e}} \\frac{d}{d\\eta} \\mathcal I_{-1/2}(\\eta),

where :math:`\\lambda` is a correction factor; :math:`\\lambda = 1/9` for the true gradient corrected Thomas-Fermi model
and :math:`\\lambda = 1` for the traditional von Weissaecker model, :math:`\\mathcal I_{-1/2}[\\eta_0]` is the
Fermi Integral of order :math:`-1/2`, and :math:`\\Lambda_e` is the de Broglie wavelength of the electrons.

In the case :math:`\\nu < 1` the EGS potential takes the form

.. math::
   U_{ab}(r) = \\frac{Z_a Z_b \\bar{e}^2 }{2r}\\left [ ( 1+ \\alpha ) e^{-r/\\lambda_-} + ( 1 - \\alpha) e^{-r/\\lambda_+} \\right ],

with

.. math::
   \\lambda_\\pm^2 = \\frac{\\nu \\lambda_{\\textrm{TF}}^2}{2b \\pm 2b\\sqrt{1 - \\nu}}, \\quad \\alpha = \\frac{b}{\\sqrt{b - \\nu}},

where the parameter :math:`b` arises from exchange-correlation contributions, see below.\n
On the other hand :math:`\\nu > 1`, the pair potential has the form

.. math::
   U_{ab}(r) = \\frac{Z_a Z_b \\bar{e}^2}{r}\\left [ \\cos(r/\\gamma_-) + \\alpha' \\sin(r/\\gamma_-) \\right ] e^{-r/\\gamma_+}

with

.. math::
   \\gamma_\\pm^2 = \\frac{\\nu\\lambda_{\\textrm{TF}}^2}{\\sqrt{\\nu} \\pm b}, \\quad \\alpha' = \\frac{b}{\\sqrt{\\nu - b}}.

Neglect of exchange-correlational effects leads to :math:`b = 1` otherwise

.. math::
   b = 1 - \\frac{2}{8} \\frac{1}{k_{\\textrm{F}}^2 \\lambda_{\\textrm{TF}}^2 }  \\left [ h\\left ( \\Theta \\right ) - 2 \\Theta h'(\\Theta) \\right ]

where :math:`k_{\\textrm{F}}` is the Fermi wavenumber and :math:`\\Theta = (\\beta E_{\\textrm{F}})^{-1}` is the electron
degeneracy parameter` calculated from the Fermi energy.

.. math::
   h \\left ( \\Theta \\right) = \\frac{N(\\Theta)}{D(\\Theta)}\\tanh \\left( \\Theta^{-1} \\right ),

.. math::
   N(\\Theta) = 1 + 2.8343\\Theta^2 - 0.2151\\Theta^3 + 5.2759\\Theta^4,

.. math::
   D \\left ( \\Theta \\right ) = 1 + 3.9431\\Theta^2 + 7.9138\\Theta^4.

Force Error
***********

The EGS potential is always smaller than pure Yukawa. Therefore the force error is chosen to be the same as Yukawa's

.. math::

    \\Delta F = \\frac{q^2}{4 \\pi \\epsilon_0} \\sqrt{\\frac{2 \\pi n}{\\lambda_{-}}}e^{-r_c/\\lambda_-}

This overestimates it, but it doesn't matter.

Potential Attributes
********************

The elements of :attr:`sarkas.potentials.core.Potential.pot_matrix` are

if :attr:`sarkas.core.Parameters.nu` less than 1:

.. code-block::

    pot_matrix[0] = q_iq_j/4pi eps0
    pot_matrix[1] = nu
    pot_matrix[2] = 1 + alpha
    pot_matrix[3] = 1 - alpha
    pot_matrix[4] = 1.0 / lambda_minus
    pot_matrix[5] = 1.0 / lambda_plus

else

.. code-block::

    pot_matrix[0] = q_iq_j/4pi eps0
    pot_matrix[1] = nu
    pot_matrix[2] = 1.0
    pot_matrix[3] = alpha prime
    pot_matrix[4] = 1.0 / gamma_minus
    pot_matrix[5] = 1.0 / gamma_plus

"""
from numpy import cos, cosh, exp, pi, sin, sqrt, tanh, zeros
from numba import jit
from numba.core.types import float64, UniTuple

from ..utilities.exceptions import AlgorithmError
from ..utilities.maths import force_error_analytic_pp, fd_integral


def update_params(potential, params):
    """
    Assign potential dependent simulation's parameters.

    Parameters
    ----------
    potential : :class:`sarkas.potentials.core.Potential`
        Class handling potential form.

    params : :class:`sarkas.core.Parameters`
        Simulation's parameters.

    Raises
    ------
    `~sarkas.utilities.exceptions.AlgorithmError`
        If the chosen algorithm is pppm.

    """

    # lambda factor : 1 = von Weizsaecker, 1/9 = Thomas-Fermi
    if not hasattr(potential, "lmbda"):
        potential.lmbda = 1.0 / 9.0

    # eq. (14) of Ref. [1]_
    params.nu = 3.0 / pi ** 1.5 * params.landau_length / params.lambda_deB
    dIdeta = - 3.0/2.0 * fd_integral(params.eta_e, -1.5)
    params.nu *= potential.lmbda * dIdeta

    # Degeneracy Parameter
    theta = params.electron_degeneracy_parameter
    if 0.1 <= theta <= 12:
        # Regime of validity of the following approximation Perrot et al. Phys Rev A 302619 (1984)
        # eq. (33) of Ref. [1]_
        Ntheta = 1.0 + 2.8343 * theta ** 2 - 0.2151 * theta ** 3 + 5.2759 * theta ** 4
        # eq. (34) of Ref. [1]_
        Dtheta = 1.0 + 3.9431 * theta ** 2 + 7.9138 * theta ** 4
        # eq. (32) of Ref. [1]_
        h = Ntheta / Dtheta * tanh(1.0 / theta)
        # grad h(x)
        gradh = -(Ntheta / Dtheta) / cosh(1 / theta) ** 2 / (theta ** 2) - tanh(  # derivative of tanh(1/x)
            1.0 / theta
        ) * (
            Ntheta * (7.8862 * theta + 31.6552 * theta ** 3) / Dtheta ** 2  # derivative of 1/Dtheta
            + (5.6686 * theta - 0.6453 * theta ** 2 + 21.1036 * theta ** 3) / Dtheta
        )  # derivative of Ntheta
        # eq.(31) of Ref. [1]_
        b = 1.0 - 2.0 / (8.0 * (params.kF * params.lambda_TF) ** 2) * (h - 2.0 * theta * gradh)
    else:
        b = 1.0

    params.b = b

    # Monotonic decay
    if params.nu <= 1:
        # eq. (29) of Ref. [1]_
        params.lambda_p = params.lambda_TF * sqrt(params.nu / (2.0 * b + 2.0 * sqrt(b ** 2 - params.nu)))
        params.lambda_m = params.lambda_TF * sqrt(params.nu / (2.0 * b - 2.0 * sqrt(b ** 2 - params.nu)))
        params.alpha = b / sqrt(b - params.nu)

    # Oscillatory behavior
    if params.nu > 1:
        # eq. (29) of Ref. [1]_
        params.gamma_m = params.lambda_TF * sqrt(params.nu / (sqrt(params.nu) - b))
        params.gamma_p = params.lambda_TF * sqrt(params.nu / (sqrt(params.nu) + b))
        params.alphap = b / sqrt(params.nu - b)

    potential.matrix = zeros((7, params.num_species, params.num_species))

    potential.matrix[1, :, :] = params.nu

    for i, q1 in enumerate(params.species_charges):

        for j, q2 in enumerate(params.species_charges):

            if params.nu <= 1:
                potential.matrix[0, i, j] = q1 * q2 / (2.0 * params.fourpie0)
                potential.matrix[2, i, j] = 1.0 + params.alpha
                potential.matrix[3, i, j] = 1.0 - params.alpha
                potential.matrix[4, i, j] = 1.0 / params.lambda_m
                potential.matrix[5, i, j] = 1.0 / params.lambda_p

            if params.nu > 1:
                potential.matrix[0, i, j] = q1 * q2 / params.fourpie0
                potential.matrix[2, i, j] = 1.0
                potential.matrix[3, i, j] = params.alphap
                potential.matrix[4, i, j] = 1.0 / params.gamma_m
                potential.matrix[5, i, j] = 1.0 / params.gamma_p

    potential.matrix[6, :, :] = potential.a_rs

    if potential.method == "pppm":
        raise AlgorithmError("pppm algorithm not implemented yet.")

    potential.force = egs_force
    # EGS is always smaller than pure Yukawa.
    # Therefore the force error is chosen to be the same as Yukawa's.
    # This overestimates it, but it doesn't matter.

    # The rescaling constant is sqrt ( na^4 ) = sqrt( 3 a/(4pi) )
    params.force_error = force_error_analytic_pp(
        potential.type, potential.rc, potential.matrix, sqrt(3.0 * params.a_ws / (4.0 * pi))
    )


@jit(UniTuple(float64, 2)(float64, float64[:]), nopython=True)
def egs_force(r_in, pot_matrix):
    """
    Numba'd function to calculate the potential and force between particles using the EGS Potential.

    Parameters
    ----------
    r_in : float
        Particles' distance.

    pot_matrix : array
        EGS potential parameters. \n
        Shape = (6, :attr:`sarkas.core.Parameters.num_species`, :attr:`sarkas.core.Parameters.num_species`)

    Returns
    -------
    U : float
        Potential.

    fr : float
        Force.

    Examples
    --------
    >>> from numpy import array, pi
    >>> from scipy.constants import epsilon_0
    >>> r = 2.0
    >>> alpha = 1.3616
    >>> lambda_p = 1.778757e-09
    >>> lambda_m = 4.546000e-09
    >>> charge = 1.440961e-09
    >>> c_const = charge**2/( 4.0 * pi * epsilon_0)
    >>> pot_mat = array([c_const * 0.5, 1.0 + alpha, 1.0 - alpha, 1.0/lambda_m, 1.0 / lambda_p, 1.0e-14])
    >>> egs_force(r, pot_mat)
    (-0.9067719924627385, 270184640.33105946)


    """

    rs = pot_matrix[6]
    # Branchless programming
    r = r_in * (r_in >= rs) + rs * (r_in < rs)

    # nu = pot_matrix[1]
    if pot_matrix[1] <= 1.0:
        temp1 = pot_matrix[2] * exp(-r * pot_matrix[4])
        temp2 = pot_matrix[3] * exp(-r * pot_matrix[5])
        # Potential
        U = (temp1 + temp2) * pot_matrix[0] / r
        # Force
        fr = U / r + pot_matrix[0] * (temp1 * pot_matrix[4] + temp2 * pot_matrix[5]) / r

    else:
        coskr = cos(r * pot_matrix[4])
        sinkr = sin(r * pot_matrix[4])
        expkr = pot_matrix[0] * exp(-r * pot_matrix[5])
        U = (coskr + pot_matrix[3] * sinkr) * expkr / r
        fr = U / r  # derivative of 1/r
        fr += U * pot_matrix[5]  # derivative of exp
        fr += pot_matrix[4] * (sinkr - pot_matrix[3] * coskr) * expkr / r

    return U, fr
