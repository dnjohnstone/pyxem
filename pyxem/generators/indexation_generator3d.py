# -*- coding: utf-8 -*-
# Copyright 2017-2019 The pyXem developers
#
# This file is part of pyXem.
#
# pyXem is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyXem is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyXem.  If not, see <http://www.gnu.org/licenses/>.

"""Indexation generator and associated tools.

"""

import numpy as np
import hyperspy.api as hs

from pyxem.signals.indexation_results import TemplateMatchingResults
from pyxem.signals.indexation_results import VectorMatchingResults

from pyxem.signals import transfer_navigation_axes

from pyxem.utils.indexation_utils import correlate_library
from pyxem.utils.indexation_utils import index_magnitudes
from pyxem.utils.indexation_utils import match_vectors
from pyxem.utils.indexation_utils import OrientationResult
from pyxem.utils.indexation_utils import get_nth_best_solution

from collections import namedtuple
from operator import attrgetter

from transforms3d.euler import mat2euler, euler2mat
from pyxem.utils.vector_utils import detector_to_fourier
from diffsims.utils.sim_utils import get_electron_wavelength

import lmfit


def _refine_best_orientations(single_match_result,
                              vectors,
                              library,
                              beam_energy,
                              camera_length,
                              n_best=5,
                              rank=0,
                              index_error_tol=0.2,
                              method="leastsq",
                              vary_angles=True,
                              vary_center=False,
                              vary_scale=False,
                              verbose=False
                              ):
    """
    Refine a single orientation against the given cartesian vector coordinates.

    Parameters
    ----------
    single_match_result : VectorMatchingResults
        Pool of solutions from the vector matching algorithm
    n_best : int
        Refine the best `n` orientations starting from `rank`.
        With `n_best=0` (default), all orientations are refined.
    rank : int
        The rank of the solution to start from.
    solution : list
        np.array containing the initial orientation
    vectors : DiffractionVectors3D
        DiffractionVectors3D to be indexed.
    structure_library : :obj:`diffsims:StructureLibrary` Object
        Dictionary of structures and associated orientations for which
        electron diffraction is to be simulated.
    index_error_tol : float
        Max allowed error in peak indexation for classifying it as indexed,
        calculated as :math:`|hkl_calculated - round(hkl_calculated)|`.
    method : str
        Minimization algorithm to use, choose from:
        'leastsq', 'nelder', 'powell', 'cobyla', 'least-squares'.
        See `lmfit` documentation (https://lmfit.github.io/lmfit-py/fitting.html)
        for more information.
    vary_angles : bool,
        Free the euler angles (rotation matrix) during the refinement.
    vary_center : bool
        Free the center of the diffraction pattern (beam center) during the refinement.
    vary_scale : bool
        Free the scale (i.e. pixel size) of the diffraction vectors during refinement.

    Returns
    -------
    result : OrientationResult
        Container for the orientation refinement results
    """
    if not isinstance(single_match_result[0], tuple):  # pragma: no cover
        single_match_result = single_match_result[0]
    n_matches = len(single_match_result)

    if n_best == 0:
        n_best = n_matches - rank

    n_best = min(n_matches, n_best)

    top_matches = np.empty(n_best, dtype="object")
    res_rhkls = []

    for i in range(rank, rank + n_best):
        if verbose:  # pragma: no cover
            print(f"# {i}/{n_best} ({n_matches})")

        solution = get_nth_best_solution(single_match_result, rank=i)

        result = _refine_orientation(solution,
                                     vectors,
                                     library,
                                     beam_energy=beam_energy,
                                     camera_length=camera_length,
                                     index_error_tol=index_error_tol,
                                     method=method,
                                     vary_angles=vary_angles,
                                     vary_center=vary_center,
                                     vary_scale=vary_scale,
                                     verbose=verbose)

        top_matches[i] = result[0]
        res_rhkls.append(result[1])

    res = np.empty(2, dtype=np.object)
    res[0] = top_matches
    res[1] = np.asarray(res_rhkls)
    return res


def _refine_orientation(solution,
                        k_xy,
                        structure_library,
                        beam_energy,
                        camera_length,
                        index_error_tol=0.2,
                        method="leastsq",
                        vary_angles=True,
                        vary_center=False,
                        vary_scale=False,
                        verbose=False,
                        ):
    """
    Refine a single orientation against the given cartesian vector coordinates.

    Parameters
    ----------
    solution : OrientationResult
        Namedtuple containing the starting orientation
    k_xy : DetectorCoordinates2D
        DetectorCoordinates2D (x,y pixel format) to be indexed.
    structure_library : :obj:`diffsims:StructureLibrary` Object
        Dictionary of structures and associated orientations for which
        electron diffraction is to be simulated.
    index_error_tol : float
        Max allowed error in peak indexation for classifying it as indexed,
        calculated as :math:`|hkl_calculated - round(hkl_calculated)|`.
    method : str
        Minimization algorithm to use, choose from:
        'leastsq', 'nelder', 'powell', 'cobyla', 'least-squares'.
        See `lmfit` documentation (https://lmfit.github.io/lmfit-py/fitting.html)
        for more information.
    vary_angles : bool,
        Free the euler angles (rotation matrix) during the refinement.
    vary_center : bool
        Free the center of the diffraction pattern (beam center) during the refinement.
    vary_scale : bool
        Free the scale (i.e. pixel size) of the diffraction vectors during refinement.
    verbose : bool
        Be more verbose

    Returns
    -------
    result : OrientationResult
        Container for the orientation refinement results
    """
    # prepare reciprocal_lattice
    structure = structure_library.structures[solution.phase_index]
    lattice_recip = structure.lattice.reciprocal()

    def objfunc(params, k_xy, lattice_recip, wavelength, camera_length):
        cx = params["center_x"].value
        cy = params["center_y"].value
        ai = params["ai"].value
        aj = params["aj"].value
        ak = params["ak"].value
        scale = params["scale"].value

        rotmat = euler2mat(ai, aj, ak)

        k_xy = (k_xy + np.array((cx, cy)) * scale)
        cart = detector_to_fourier(k_xy, wavelength, camera_length)

        intermediate = cart.dot(rotmat.T)  # Must use the transpose here
        hklss = lattice_recip.fractional(intermediate) * scale

        rhklss = np.rint(hklss)
        ehklss = np.abs(hklss - rhklss)

        return ehklss

    ai, aj, ak = mat2euler(solution.rotation_matrix)

    params = lmfit.Parameters()
    params.add("center_x", value=solution.center_x, vary=vary_center)
    params.add("center_y", value=solution.center_y, vary=vary_center)
    params.add("ai", value=ai, vary=vary_angles)
    params.add("aj", value=aj, vary=vary_angles)
    params.add("ak", value=ak, vary=vary_angles)
    params.add("scale", value=solution.scale, vary=vary_scale, min=0.8, max=1.2)

    wavelength = get_electron_wavelength(beam_energy)
    camera_length = camera_length * 1e10
    args = k_xy, lattice_recip, wavelength, camera_length

    res = lmfit.minimize(objfunc, params, args=args, method=method)

    if verbose:  # pragma: no cover
        lmfit.report_fit(res)

    p = res.params

    ai, aj, ak = p["ai"].value, p["aj"].value, p["ak"].value
    scale = p["scale"].value
    center_x = params["center_x"].value
    center_y = params["center_y"].value

    rotation_matrix = euler2mat(ai, aj, ak)

    k_xy = (k_xy + np.array((center_x, center_y)) * scale)
    cart = detector_to_fourier(k_xy, wavelength=wavelength,
                               camera_length=camera_length)

    intermediate = cart.dot(rotation_matrix.T)  # Must use the transpose here
    hklss = lattice_recip.fractional(intermediate)

    rhklss = np.rint(hklss)

    error_hkls = res.residual.reshape(-1, 3)
    error_mean = np.mean(error_hkls)

    valid_peak_mask = np.max(error_hkls, axis=-1) < index_error_tol
    valid_peak_count = np.count_nonzero(valid_peak_mask, axis=-1)

    num_peaks = len(k_xy)

    match_rate = (valid_peak_count * (1 / num_peaks)) if num_peaks else 0

    orientation = OrientationResult(phase_index=solution.phase_index,
                                    rotation_matrix=rotation_matrix,
                                    match_rate=match_rate,
                                    error_hkls=error_hkls,
                                    total_error=error_mean,
                                    scale=scale,
                                    center_x=center_x,
                                    center_y=center_y)

    res = np.empty(2, dtype=np.object)
    res[0] = orientation
    res[1] = rhklss

    return res


class IndexationGenerator3D():
    """Generates an indexer for DiffractionVectors3D using a number of methods.

    Attributes
    ----------
    vectors : DiffractionVectors3D
        DiffractionVectors3D to be indexed.
    vector_library : DiffractionVectorLibrary
        Library of theoretical diffraction vector magnitudes and inter-vector
        angles for indexation.

    Parameters
    ----------
    vectors : DiffractionVectors3D
        DiffractionVectors3D to be indexed.
    vector_library : DiffractionVectorLibrary
        Library of theoretical diffraction vector magnitudes and inter-vector
        angles for indexation.
    """

    def __init__(self,
                 vectors,
                 vector_library):
        self.vectors = vectors
        self.library = vector_library

    def index_vectors(self,
                      mag_tol,
                      angle_tol,
                      index_error_tol,
                      n_peaks_to_index,
                      n_best,
                      *args,
                      **kwargs):
        """Assigns hkl indices to diffraction vectors.

        Parameters
        ----------
        mag_tol : float
            The maximum absolute error in diffraction vector magnitude, in units
            of reciprocal Angstroms, allowed for indexation.
        angle_tol : float
            The maximum absolute error in inter-vector angle, in units of
            degrees, allowed for indexation.
        index_error_tol : float
            Max allowed error in peak indexation for classifying it as indexed,
            calculated as :math:`|hkl_calculated - round(hkl_calculated)|`.
        n_peaks_to_index : int
            The maximum number of peak to index.
        n_best : int
            The maximum number of good solutions to be retained.
        *args : arguments
            Arguments passed to the map() function.
        **kwargs : arguments
            Keyword arguments passed to the map() function.

        Returns
        -------
        indexation_results : VectorMatchingResults
            Navigation axes of the diffraction vectors signal containing vector
            indexation results for each probe position.
        """
        matched = self.vectors.map(match_vectors,
                                   library=self.library,
                                   mag_tol=mag_tol,
                                   angle_tol=np.deg2rad(angle_tol),
                                   index_error_tol=index_error_tol,
                                   n_peaks_to_index=n_peaks_to_index,
                                   n_best=n_best,
                                   inplace=False,
                                   *args,
                                   **kwargs)
        indexation = matched.isig[0]
        rhkls = matched.isig[1].data

        indexation_results = VectorMatchingResults(indexation)
        indexation_results.vectors = self.vectors
        indexation_results.hkls = rhkls
        indexation_results = transfer_navigation_axes(indexation_results,
                                                      self.vectors)

        self.vectors.hkls = rhkls

        return indexation_results

    def refine_best_orientation(self,
                                orientations,
                                beam_energy,
                                camera_length,
                                rank=0,
                                index_error_tol=0.2,
                                vary_angles=True,
                                vary_center=False,
                                vary_scale=False,
                                method="leastsq"):
        """Refines the best orientation and assigns hkl indices to diffraction
        vectors.

        Parameters
        ----------
        rank : int
            The rank of the solution, i.e. rank=2 refines the third best solution
        index_error_tol : float
            Max allowed error in peak indexation for classifying it as indexed,
            calculated as :math:`|hkl_calculated - round(hkl_calculated)|`.
        method : str
            Minimization algorithm to use, choose from:
            'leastsq', 'nelder', 'powell', 'cobyla', 'least-squares'.
            See `lmfit` documentation (https://lmfit.github.io/lmfit-py/fitting.html)
            for more information.
        vary_angles : bool,
            Free the euler angles (rotation matrix) during the refinement.
        vary_center : bool
            Free the center of the diffraction pattern (beam center) during the refinement.
        vary_scale : bool
            Free the scale (i.e. pixel size) of the diffraction vectors during refinement.

        Returns
        -------
        indexation_results : IndexationResults
            Navigation axes of the diffraction vectors signal containing
            indexation results for each probe position.
        """
        vectors = self.vectors
        library = self.library

        return self.refine_n_best_orientations(orientations,
                                               beam_energy=beam_energy,
                                               camera_length=camera_length,
                                               n_best=1,
                                               rank=rank,
                                               index_error_tol=index_error_tol,
                                               method=method,
                                               vary_angles=vary_angles,
                                               vary_center=vary_center,
                                               vary_scale=vary_scale)

    def refine_n_best_orientations(self,
                                   orientations,
                                   beam_energy,
                                   camera_length,
                                   n_best=0,
                                   rank=0,
                                   index_error_tol=0.2,
                                   vary_angles=True,
                                   vary_center=False,
                                   vary_scale=False,
                                   method="leastsq"):
        """Refines the best orientation and assigns hkl indices to diffraction vectors.

        Parameters
        ----------
        orientations : VectorMatchingResults
            List of orientations to refine, must be an instance of `VectorMatchingResults`.
        beam_energy : float
            The acceleration voltage with which the data was acquired.
        camera_length : float
            The camera length in meters.
        n_best : int
            Refine the best `n` orientations starting from `rank`.
            With `n_best=0` (default), all orientations are refined.
        rank : int
            The rank of the solution to start from.
        index_error_tol : float
            Max allowed error in peak indexation for classifying it as indexed,
            calculated as :math:`|hkl_calculated - round(hkl_calculated)|`.
        method : str
            Minimization algorithm to use, choose from:
            'leastsq', 'nelder', 'powell', 'cobyla', 'least-squares'.
            See `lmfit` documentation (https://lmfit.github.io/lmfit-py/fitting.html)
            for more information.
        vary_angles : bool,
            Free the euler angles (rotation matrix) during the refinement.
        vary_center : bool
            Free the center of the diffraction pattern (beam center) during the refinement.
        vary_scale : bool
            Free the scale (i.e. pixel size) of the diffraction vectors during refinement.

        Returns
        -------
        indexation_results : VectorMatchingResults
            Navigation axes of the diffraction vectors signal containing vector
            indexation results for each probe position.
        """
        vectors = self.vectors
        library = self.library

        matched = orientations.map(_refine_best_orientations,
                                   vectors=vectors,
                                   library=library,
                                   beam_energy=beam_energy,
                                   camera_length=camera_length,
                                   n_best=n_best,
                                   rank=rank,
                                   method="leastsq",
                                   verbose=False,
                                   vary_angles=vary_angles,
                                   vary_center=vary_center,
                                   vary_scale=vary_scale,
                                   inplace=False, parallel=False)

        indexation = matched.isig[0]
        rhkls = matched.isig[1].data

        indexation_results = VectorMatchingResults(indexation)
        indexation_results.vectors = vectors
        indexation_results.hkls = rhkls
        indexation_results = transfer_navigation_axes(indexation_results,
                                                      vectors.cartesian)

        return indexation_results