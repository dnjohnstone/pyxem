# Test Coverage Analysis for pyxem

This document identifies areas of the codebase where test coverage is weakest
and proposes concrete improvements. Findings are ranked by estimated impact.

---

## Summary

The test suite is broadly well-structured, with test directories mirroring
source directories and most modules having at least one corresponding test
file. However, depth of coverage varies enormously. Several large, complex
modules have only a handful of tests, and a number of individual functions
and methods have no tests at all.

---

## Priority 1 — Critical gaps (large modules, few or no tests)

### 1. `utils/indexation_utils.py` — 1715 lines, only 4 tests

This is the most severe gap in the codebase. The file contains the core
template-matching and vector-indexation algorithms, yet `test_indexation_utils.py`
covers only four utility functions.

**Tested** (4 of ~28 public/semi-public functions):
- `zero_mean_normalized_correlation`
- `fast_correlation`
- `match_vectors` (one happy-path test + one edge-case)

**Completely untested** (selection of the most impactful):
- `get_nth_best_solution` — ranking/selecting indexation solutions
- `index_magnitudes` — magnitude-based indexation
- `get_in_plane_rotation_correlation` — in-plane rotation matching
- `correlate_library_to_pattern` / `_fast` / `_partial` — the three main
  correlation entry points used by `IndexationGenerator`
- `get_n_best_matches` — filtering best matches from a correlation result
- `index_dataset_with_template_rotation` — end-to-end dataset indexation
- `_simulations_to_arrays`, `_cartesian_positions_to_polar`,
  `_match_polar_to_polar_template`, `_match_polar_to_polar_library`,
  `_mixed_matching_lib_to_polar`, `_get_integrated_polar_templates`,
  `_prepare_image_and_templates`, `_renormalize_polar_block`

**Recommended tests:**
- Unit tests for each public entry point with known synthetic inputs whose
  expected output can be computed by hand or with a reference implementation.
- Parametrised tests exercising the `fast`, `partial`, and default correlation
  paths against a small toy diffraction library.
- Tests for `get_n_best_matches` verifying that the correct top-N results are
  returned and that the output array shape is correct.
- Edge-case tests: zero-intensity pattern, single-candidate library, all
  correlations equal.

---

### 2. `utils/expt_utils.py` — 714 lines, ~9 of 20 functions untested

`expt_utils` contains the pixel-level image-processing primitives that underpin
most of `Diffraction2D`. About half the functions lack direct tests.

**Untested functions:**
- `gain_normalise(z, dref, bref)` — flat-field correction
- `convert_affine_to_transform(D, shape)` — affine matrix → SciPy warp format
- `apply_transformation(z, transformation, keep_dtype, order)` — applies the
  affine warp
- `regional_filter(z, h)` — h-dome background subtraction
- `circular_mask(shape, radius, center)` — generates a boolean mask
- `reference_circle(coords, dimX, dimY, radius)` — reference ring for
  calibration
- `integrate_radially(z, azimuthal_integrator, ...)` — radial integration
  (distinct from the 1-D and 2-D azimuthal variants that are tested)
- `medfilt_1d(z, azimuthal_integrator, npt_rad, npt_azim, ...)` — median
  filter in polar coordinates
- `sigma_clip(z, azimuthal_integrator, npt_rad, npt_azim, ...)` — sigma-clip
  integration

**Recommended tests:**
- `gain_normalise`: compare output against manual computation for a known dark
  reference and bright reference.
- `convert_affine_to_transform` + `apply_transformation`: round-trip test
  (apply a pure translation, check that peak positions shift by the expected
  amount).
- `circular_mask`: verify that pixels inside `radius` are `True` and outside
  are `False`; test with a non-centred `center` argument.
- `regional_filter`: known flat background with a local bright feature;
  verify the feature is suppressed.
- `medfilt_1d` / `sigma_clip` / `integrate_radially`: use a synthetic radial
  pattern with a known integral; confirm the output matches.

---

### 3. `utils/ri_utils.py` — 193 lines, no dedicated tests

This file contains all damping functions used by `ReducedIntensity1D` to
prepare signals for PDF conversion. They are exercised only indirectly through
the `ReducedIntensityGenerator1D` workflow, meaning a bug in a damping
function may go undetected.

**Untested functions:**
- `subtract_pattern`
- `mask_from_pattern`
- `damp_ri_exponential`
- `damp_ri_lorch`
- `damp_ri_updated_lorch`
- `damp_ri_low_q_region_erfc`

**Recommended tests:**
- For each damping function, pass a known constant array and verify the output
  matches the analytical result (e.g., for `damp_ri_exponential` with `b=0`
  the output must equal the input; for large `b` values the high-s end of the
  array must be suppressed toward zero).
- `subtract_pattern`: verify that `z - pattern` is returned exactly.
- `mask_from_pattern`: verify that zeros in the pattern zero-out the
  corresponding elements of `z`.
- Edge cases: zero-length array, `s_max = 0` for the Lorch variants
  (expected `nan_to_num` behaviour).

---

## Priority 2 — Important modules with significant method-level gaps

### 4. `signals/diffraction2d.py` — 2512 lines, several methods untested

`Diffraction2D` is the central signal class. Its test file is the largest in
the repo, but a number of methods have no test at all.

**Methods with no identifiable test:**
- `rotate_diffraction(angle)` — in-place rotation of the diffraction pattern
- `flip_diffraction_x()` / `flip_diffraction_y()` — axis flips
- `angular_mask(angle0, angle1, ...)` — sector masking
- `apply_gain_normalisation(dref, bref, gain_normalisation)` — flat-field
  correction at signal level
- `add_peak_array_as_markers(peaks, ...)` — adds HyperSpy markers
- `add_ellipse_array_as_markers(ellipses, ...)` — adds ellipse markers
- `template_match_disk`, `template_match_ring`,
  `template_match_with_binary_image` — need verification that these are
  exercised; they rely on dask_tools helpers that are tested, but the
  high-level wrappers may not be

**Recommended tests:**
- `rotate_diffraction`: rotate by 90°, compare to `np.rot90` output.
- `flip_diffraction_x` / `flip_diffraction_y`: verify data is reversed along
  the correct axis.
- `angular_mask`: check that the returned mask is `True` only within the
  specified angular sector.
- `apply_gain_normalisation`: a single-frame test with known dark/bright
  references; compare result to manual computation.
- `add_peak_array_as_markers` / `add_ellipse_array_as_markers`: smoke tests
  verifying that `signal.metadata` (or the HyperSpy marker list) is populated
  after calling the method.
- `template_match_*`: at minimum a smoke test that the method runs and returns
  a signal of the expected shape.

---

### 5. `signals/differential_phase_contrast.py` — 834 lines, 3 methods untested

The DPC signal is well-tested overall, but three methods are missing:

- `DPCSignal2D.gaussian_blur(sigma)` — smoothing filter
- `DPCSignal2D.rotate_data(angle)` — rotate the 2-D complex field
- `DPCSignal2D.to_beamshift()` / `DPCSignal1D.to_beamshift()` — conversion
  to `BeamShift` signal type

**Recommended tests:**
- `gaussian_blur`: verify the output is smoother than the input (e.g., reduced
  variance); check that the metadata / axes are preserved.
- `rotate_data`: rotate by 180° and verify the output equals the negative of
  the input (for a real-valued case).
- `to_beamshift`: verify the returned object is a `BeamShift` instance and
  that data values and axes are preserved.

---

### 6. `signals/diffraction_vectors.py` — 719 lines, classmethod and helper untested

- `DiffractionVectors.from_peaks(peaks, center, calibration)` — the primary
  constructor used in production workflows; converting from peak arrays is a
  critical path.
- `generate_marker_inputs_from_peaks(peaks)` — helper used to generate
  HyperSpy markers; currently no test.

**Recommended tests:**
- `from_peaks`: construct a `DiffractionVectors` object from a known peak
  array and verify coordinate values after center subtraction and calibration.
- `generate_marker_inputs_from_peaks`: pass a known ragged peak array and
  verify the output is in the format expected by HyperSpy markers.

---

## Priority 3 — Small but complete gaps

### 7. `utils/signal.py` — 3 of 4 functions untested

`test_signal_utils.py` only tests `select_method_from_method_dict` (and only
the `NotImplementedError` and help-printing branches). The three
axis-transfer utilities are untested:

- `transfer_signal_axes(new_signal, old_signal)` — copies signal axis
  calibrations (scale, units, name)
- `transfer_navigation_axes(new_signal, old_signal)` — copies navigation axis
  calibrations
- `transfer_navigation_axes_to_signal_axes(new_signal, old_signal)` —
  promotes navigation axes to signal axes on the new signal

These are used heavily throughout the generators but have no direct tests,
making calibration regressions hard to detect.

**Recommended tests:**
- Create a pair of simple HyperSpy signals with known axis calibrations; call
  each transfer function and assert that scale, units, and name match.
- Test the edge case where `new_signal` has fewer dimensions than `old_signal`.

---

### 8. `utils/virtual_images_utils.py` — `normalize_virtual_images` untested

The file has two functions. `get_vectors_mesh` is well-tested.
`normalize_virtual_images(im)` has no test.

**Recommended test:**
- Pass an array with a known maximum; verify the output maximum is 1.0 and
  all other values are scaled proportionally.
- Edge case: all-zero image (division by zero).

---

### 9. `utils/pdf_utils.py` — `normalise_pdf_signal_to_max` untested directly

The single function in this module is exercised only as part of the
`PairDistributionFunction1D` workflow.

**Recommended test:**
- Pass an array with a known maximum and a non-zero `index_min`; verify that
  the output is divided by the correct max value.
- Verify that values before `index_min` can exceed 1.0 (i.e., the normalisation
  is computed on the sliced region only).

---

### 10. `utils/big_data_utils.py` — internal helpers untested

Only `chunked_application_of_UDF` (the public entry point) and
`_get_chunk_size` (input validation) are tested. The intermediate helpers
(`_load_and_cast`, `_factory`, `_create_columns`,
`_combine_list_into_navigation_space`) have no tests.

**Recommended tests:**
- `_create_columns` / `_combine_list_into_navigation_space`: unit tests with
  small in-memory arrays to verify correct stitching of results.

---

## Priority 4 — Intentionally excluded files worth revisiting

The following files are excluded from being run as test modules via
`pytest.ini` (legacy guard against pytest collecting source files as test
targets), but their corresponding test files do exist and run correctly. The
issue is that some excluded modules have **no test file at all**:

| Module | Has test file? | Notes |
|---|---|---|
| `signals/common_diffraction.py` | No | Base-class mixin; methods are exercised through subclasses but no direct unit tests |
| `signals/indexation_results.py` | No | `IndexationResults` signal; exercised only as output of indexation workflows |
| `utils/marker_tools.py` | Yes (`test_marker_tools.py`) | Covered |

**Recommendation:** Add a `test_common_diffraction.py` that instantiates the
mixin on a minimal HyperSpy signal and tests `get_direct_beam_mask`,
`apply_affine_transformation`, and other methods that are defined on the base
class and inherited by all diffraction signal types.

---

## Suggested prioritisation for a test-writing sprint

| # | Module | Estimated effort | Expected impact |
|---|---|---|---|
| 1 | `utils/indexation_utils.py` | High | High — core algorithm, no regression protection |
| 2 | `utils/expt_utils.py` | Medium | High — pixel-level primitives used everywhere |
| 3 | `utils/ri_utils.py` | Low | Medium — pure numeric functions, easy to test |
| 4 | `signals/diffraction2d.py` (missing methods) | Medium | Medium — most-used signal class |
| 5 | `utils/signal.py` (axis transfer) | Low | Medium — silent calibration bugs possible |
| 6 | `signals/differential_phase_contrast.py` | Low | Medium — 3 untested methods |
| 7 | `signals/diffraction_vectors.py` | Low | Medium — `from_peaks` is a critical constructor |
| 8 | `utils/pdf_utils.py` / `utils/virtual_images_utils.py` | Very low | Low — single functions |
| 9 | `utils/big_data_utils.py` | Low | Low — internal helpers |
