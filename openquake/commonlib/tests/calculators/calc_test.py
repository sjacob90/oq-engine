import unittest
import numpy
from openquake.commonlib.calculators import calc

aaae = numpy.testing.assert_array_almost_equal


class TestByImt(unittest.TestCase):

    def test_data_by_imt(self):
        dda = {'r1': dict(PGA=[1, 2], PGV=[3, 4]),
               'r2': dict(PGA=[5, 6], PGV=[7, 8]),
               'r3': dict(PGA=[9, 10], PGV=[11, 12])}

        expected = {'PGA': numpy.array([{'r1': 1, 'r2': 5, 'r3': 9},
                                        {'r1': 2, 'r2': 6, 'r3': 10}]),
                    'PGV': numpy.array([{'r1': 3, 'r2': 7, 'r3': 11},
                                        {'r1': 4, 'r2': 8, 'r3': 12}])}

        actual = calc.data_by_imt(dda, ['PGA', 'PGV'], 2)
        for imt in ('PGA', 'PGV'):
            numpy.testing.assert_equal(actual[imt], expected[imt])


class HazardMapsTestCase(unittest.TestCase):

    def test_compute_hazard_map(self):
        curves = [
            [0.8, 0.5, 0.1],
            [0.98, 0.15, 0.05],
            [0.6, 0.5, 0.4],
            [0.1, 0.01, 0.001],
            [0.8, 0.2, 0.1],
        ]
        imls = [0.005, 0.007, 0.0098]
        poe = 0.2

        expected = [[0.00847798, 0.00664814, 0.0098, 0, 0.007]]
        actual = calc.compute_hazard_maps(curves, imls, poe)
        aaae(expected, actual)

    def test_compute_hazard_map_poes_list_of_one(self):
        curves = [
            [0.8, 0.5, 0.1],
            [0.98, 0.15, 0.05],
            [0.6, 0.5, 0.4],
            [0.1, 0.01, 0.001],
            [0.8, 0.2, 0.1],
        ]

        # NOTE(LB): Curves may be passed as a generator or iterator;
        # let's make sure that works, too.
        curves = iter(curves)

        imls = [0.005, 0.007, 0.0098]
        poe = [0.2]
        expected = [[0.00847798, 0.00664814, 0.0098, 0, 0.007]]
        actual = calc.compute_hazard_maps(curves, imls, poe)
        aaae(expected, actual)

    def test_compute_hazard_map_multi_poe(self):
        curves = [
            [0.8, 0.5, 0.1],
            [0.98, 0.15, 0.05],
            [0.6, 0.5, 0.4],
            [0.1, 0.01, 0.001],
            [0.8, 0.2, 0.1],
        ]
        imls = [0.005, 0.007, 0.0098]
        poes = [0.1, 0.2]
        expected = [
            [0.0098, 0.00792555, 0.0098, 0.005,  0.0098],
            [0.00847798, 0.00664814, 0.0098, 0, 0.007]
        ]
        actual = calc.compute_hazard_maps(curves, imls, poes)
        aaae(expected, actual)
