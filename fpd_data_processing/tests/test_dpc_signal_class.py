import unittest
from fpd_data_processing.pixelated_stem_class import (
        DPCBaseSignal, DPCSignal1D, DPCSignal2D)
import fpd_data_processing.pixelated_stem_tools as pst
import numpy as np


class test_dpc_signal_1d_create(unittest.TestCase):

    def test_create(self):
        data = np.ones(shape=(2, 10))
        s = DPCSignal1D(data)


class test_dpc_signal_2d_create(unittest.TestCase):

    def test_create(self):
        data = np.ones(shape=(2, 10, 10))
        s = DPCSignal2D(data)
        with self.assertRaises(ValueError):
            DPCSignal2D(np.zeros(10))


class test_dpc_signal_2d_correct_ramp(unittest.TestCase):

    def test_correct_ramp_flat(self):
        data0 = np.ones(shape=(2, 64, 64))
        s0 = DPCSignal2D(data0)
        s0_corr = s0.correct_ramp(corner_size=0.05)
        self.assertTrue((s0.data==data0).all())
        np.testing.assert_allclose(
                s0_corr.data, np.zeros_like(data0), atol=1e-8)

        s0.correct_ramp(corner_size=0.05, out=s0)
        np.testing.assert_allclose(
                s0.data, np.zeros_like(data0), atol=1e-8)

    def test_correct_ramp_x_y(self):
        array_x, array_y = np.meshgrid(range(64), range(64))
        data_x = np.swapaxes(
                np.dstack((array_x, array_x)), 0, 2).astype('float64')
        data_y = np.swapaxes(
                np.dstack((array_y, array_y)), 0, 2).astype('float64')
        s_x = DPCSignal2D(data_x)
        s_y = DPCSignal2D(data_y)
        s_x_corr = s_x.correct_ramp(corner_size=0.05)
        s_y_corr = s_y.correct_ramp(corner_size=0.05)
        np.testing.assert_allclose(
                s_x_corr.data, np.zeros_like(data_x), atol=1e-8)
        np.testing.assert_allclose(
                s_y_corr.data, np.zeros_like(data_y), atol=1e-8)

        data_xy = np.swapaxes(
                np.dstack((array_x, array_y)), 0, 2).astype('float64')
        data_yx = np.swapaxes(
                np.dstack((array_y, array_x)), 0, 2).astype('float64')
        s_xy = DPCSignal2D(data_xy)
        s_yx = DPCSignal2D(data_yx)
        s_xy_corr = s_xy.correct_ramp(corner_size=0.05)
        s_yx_corr = s_yx.correct_ramp(corner_size=0.05)
        np.testing.assert_allclose(
                s_xy_corr.data, np.zeros_like(data_xy), atol=1e-8)
        np.testing.assert_allclose(
                s_yx_corr.data, np.zeros_like(data_yx), atol=1e-8)

        data_tilt = np.swapaxes(np.dstack((
            array_x+array_y,
            np.fliplr(array_x)+array_y)), 0, 2).astype('float64')
        s_tilt = DPCSignal2D(data_tilt)
        s_tilt_corr = s_tilt.correct_ramp()
        np.testing.assert_allclose(
                s_tilt_corr.data, np.zeros_like(data_tilt), atol=1e-8)
        s_tilt.correct_ramp(out=s_tilt)
        np.testing.assert_allclose(
                s_tilt.data, np.zeros_like(data_tilt), atol=1e-8)

    def test_correct_ramp_random(self):
        array_x, array_y = np.meshgrid(range(64), range(64))
        data_tilt = np.swapaxes(np.dstack((
            array_x+array_y,
            np.fliplr(array_x)+array_y)), 0, 2).astype('float64')
        data_random = data_tilt + np.random.random(size=(2, 64, 64))*10
        s_random = DPCSignal2D(data_random)
        s_random_corr = s_random.correct_ramp()
        np.testing.assert_allclose(
                s_random_corr.data, np.zeros_like(data_random), atol=10)
        s_random.correct_ramp(out=s_random)
        np.testing.assert_allclose(
                s_random.data, np.zeros_like(data_random), atol=10)

    def test_correct_ramp_one_large_value(self):
        array_x, array_y = np.meshgrid(range(64), range(64))
        data = np.swapaxes(np.dstack((
            array_x+array_y,
            np.fliplr(array_x)+array_y)), 0, 2).astype('float64')
        data[:, 20:30, 30:40] += 1000
        s = DPCSignal2D(data)
        s_corr = s.correct_ramp()
        s_corr.data[:, 20:30, 30:40] -= 1000
        print(s_corr.data.max())
        np.testing.assert_allclose(
                s_corr.data, np.zeros_like(data), atol=1e-8)


class test_get_dpc_signal(unittest.TestCase):

    def test_get_color_signal(self):
        array_x, array_y = np.meshgrid(range(64), range(64))
        data_tilt = np.swapaxes(np.dstack((
            array_x+array_y,
            np.fliplr(array_x)+array_y)), 0, 2).astype('float64')
        data_random = data_tilt + np.random.random(size=(2, 64, 64))*10
        s_random = DPCSignal2D(data_random)
        s_random.get_color_signal()
        s_random.get_color_signal(rotation=45)

    def test_get_color_signal_zeros(self):
        s = DPCSignal2D(np.zeros((2, 100, 100)))
        s_color = s.get_color_signal()
        self.assertTrue((s_color.data['R'] == 0).all())
        self.assertTrue((s_color.data['G'] == 0).all())
        self.assertTrue((s_color.data['B'] == 0).all())

    def test_get_magnitude_signal_zeros(self):
        s = DPCSignal2D(np.zeros((2, 100, 100)))
        s_magnitude = s.get_magnitude_signal()
        self.assertTrue((s_magnitude.data == 0).all())

    def test_get_phase_signal(self):
        s = DPCSignal2D(np.zeros((2, 100, 100)))
        s.get_phase_signal()
        s.get_phase_signal(rotation=45)

    def test_get_color_image_with_indicator(self):
        s = DPCSignal2D(np.random.random(size=(2, 100, 100)))
        s.get_color_image_with_indicator()
        s.get_color_image_with_indicator(
                phase_rotation=45, indicator_rotation=10,
                autolim=True, autolim_sigma=1)


class test_dpc_signal_2d_bivariate_histogram(unittest.TestCase):

    def test_get_bivariate_histogram(self):
        array_x, array_y = np.meshgrid(range(64), range(64))
        data_tilt = np.swapaxes(np.dstack((
            array_x+array_y,
            np.fliplr(array_x)+array_y)), 0, 2).astype('float64')
        data_random = data_tilt + np.random.random(size=(2, 64, 64))*10
        s_random = DPCSignal2D(data_random)
        s_random.get_bivariate_histogram()


    def test_make_bivariate_histogram(self):
        x, y = np.ones((100, 100)), np.ones((100, 100))
        pst._make_bivariate_histogram(
                x_position=x, y_position=y,
                histogram_range=None,
                masked=None,
                bins=200,
                spatial_std=3)
