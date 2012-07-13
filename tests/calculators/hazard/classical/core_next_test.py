# Copyright (c) 2010-2012, GEM Foundation.
#
# OpenQuake is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with OpenQuake.  If not, see <http://www.gnu.org/licenses/>.


import getpass
import unittest

import kombu
import nhlib.imt

from nose.plugins.attrib import attr

from openquake.calculators.hazard.classical import core_next
from openquake.db import models
from openquake.input import logictree
from tests.utils import helpers


class ClassicalHazardCalculatorTestCase(unittest.TestCase):
    """
    Tests for the main methods of the classical hazard calculator.
    """

    def setUp(self):
        cfg = helpers.demo_file('simple_fault_demo_hazard/job.ini')
        self.job = helpers.get_hazard_job(cfg, username=getpass.getuser())
        self.calc = core_next.ClassicalHazardCalculator(self.job)

    def test_pre_execute(self):
        # Most of the pre-execute functionality is implement in other methods.
        # For this test, just make sure each method gets called.
        base_path = ('openquake.calculators.hazard.classical.core_next'
                     '.ClassicalHazardCalculator')
        init_src_patch = helpers.patch(
            '%s.%s' % (base_path, 'initialize_sources'))
        init_sm_patch = helpers.patch(
            '%s.%s' % (base_path, 'initialize_site_model'))
        init_rlz_patch = helpers.patch(
            '%s.%s' % (base_path, 'initialize_realizations'))
        patches = (init_src_patch, init_sm_patch, init_rlz_patch)

        mocks = [p.start() for p in patches]

        self.calc.pre_execute()

        for i, m in enumerate(mocks):
            self.assertEqual(1, m.call_count)
            m.stop()
            patches[i].stop()

    def test_initalize_sources(self):
        self.calc.initialize_sources()

        # The source model logic tree for this configuration has only 1 source
        # model:
        [source] = models.inputs4hcalc(
            self.job.hazard_calculation.id, input_type='source')

        parsed_sources = models.ParsedSource.objects.filter(input=source)
        # This source model contains 118 sources:
        self.assertEqual(118, len(parsed_sources))

        # Finally, check the Src2ltsrc linkage:
        [smlt] = models.inputs4hcalc(
            self.job.hazard_calculation.id, input_type='lt_source')
        [src2ltsrc] = models.Src2ltsrc.objects.filter(
            hzrd_src=source, lt_src=smlt)
        # Make sure the `filename` is exactly as it apprears in the logic tree.
        # This is import for the logic tree processing we need to do later on.
        self.assertEqual('dissFaultModel.xml', src2ltsrc.filename)

    def test_initialize_site_model(self):
        # we need a slightly different config file for this test
        cfg = helpers.demo_file(
            'simple_fault_demo_hazard/job_with_site_model.ini')
        self.job = helpers.get_hazard_job(cfg)
        self.calc = core_next.ClassicalHazardCalculator(self.job)

        self.calc.initialize_site_model()
        # If the site model isn't valid for the calculation geometry, a
        # `RuntimeError` should be raised here

        # Okay, it's all good. Now check the count of the site model records.
        [site_model_inp] = models.inputs4hcalc(
            self.job.hazard_calculation.id, input_type='site_model')
        sm_nodes = models.SiteModel.objects.filter(input=site_model_inp)

        self.assertEqual(2601, len(sm_nodes))

        num_pts_to_compute = len(
            self.job.hazard_calculation.points_to_compute())

        [site_data] = models.SiteData.objects.filter(
            hazard_calculation=self.job.hazard_calculation.id)

        # The site model is good. Now test that `site_data` was computed.
        # For now, just test the lengths of the site data collections:
        self.assertEqual(num_pts_to_compute, len(site_data.lons))
        self.assertEqual(num_pts_to_compute, len(site_data.lats))
        self.assertEqual(num_pts_to_compute, len(site_data.vs30s))
        self.assertEqual(num_pts_to_compute, len(site_data.vs30_measured))
        self.assertEqual(num_pts_to_compute, len(site_data.z1pt0s))
        self.assertEqual(num_pts_to_compute, len(site_data.z2pt5s))

    def test_initialize_site_model_no_site_model(self):
        patch_path = 'openquake.calculators.hazard.general.store_site_model'
        with helpers.patch(patch_path) as store_sm_patch:
            self.calc.initialize_site_model()
            # We should never try to store a site model in this case.
            self.assertEqual(0, store_sm_patch.call_count)

    def test_initialize_realizations(self):
        # We need initalize sources first (read logic trees, parse sources,
        # etc.)
        self.calc.initialize_sources()

        # No realizations yet:
        ltrs = models.LtRealization.objects.filter(
            hazard_calculation=self.job.hazard_calculation.id)
        self.assertEqual(0, len(ltrs))

        self.calc.initialize_realizations()

        # We expect 2 logic tree realizations
        ltr1, ltr2 = models.LtRealization.objects.filter(
            hazard_calculation=self.job.hazard_calculation.id)

        # Check each ltr contents, just to be thorough.
        self.assertEqual(0, ltr1.ordinal)
        self.assertEqual(23, ltr1.seed)
        self.assertFalse(ltr1.is_complete)
        self.assertEqual(['b1'], ltr1.sm_lt_path)
        self.assertEqual(['b1'], ltr1.gsim_lt_path)
        self.assertEqual(118, ltr1.total_sources)
        self.assertEqual(0, ltr1.completed_sources)

        self.assertEqual(1, ltr2.ordinal)
        self.assertEqual(1685488378, ltr2.seed)
        self.assertFalse(ltr2.is_complete)
        self.assertEqual(['b1'], ltr2.sm_lt_path)
        self.assertEqual(['b1'], ltr2.gsim_lt_path)
        self.assertEqual(118, ltr2.total_sources)
        self.assertEqual(0, ltr2.completed_sources)


        for ltr in (ltr1, ltr2):
            # Now check that we have source_progress records for each
            # realization.
            # Since the logic for his sample calculation only contains a single
            # source model, both samples will have the number of
            # source_progress records (that is, 1 record per source).
            src_prog = models.SourceProgress.objects.filter(
                lt_realization=ltr.id)
            self.assertEqual(118, len(src_prog))
            self.assertFalse(any([x.is_complete for x in src_prog]))

            # Check that hazard curve progress records were properly
            # initialized:
            [hc_prog_pga] = models.HazardCurveProgress.objects.filter(
                lt_realization=ltr.id, imt="PGA")
            self.assertEqual((120, 19), hc_prog_pga.result_matrix.shape)
            self.assertTrue((hc_prog_pga.result_matrix == 0).all())

            [hc_prog_sa] = models.HazardCurveProgress.objects.filter(
                lt_realization=ltr.id, imt="SA(0.025)")
            self.assertEqual((120, 19), hc_prog_sa.result_matrix.shape)
            self.assertTrue((hc_prog_sa.result_matrix == 0).all())

    @attr('slow')
    def test_execute_and_post_execute(self):
        self.calc.pre_execute()

        # Update job status to move on to the execution phase.
        self.job.is_running = True

        self.job.status = 'executing'
        self.job.save()
        self.calc.execute()

        self.job.status = 'post_executing'
        self.job.save()
        self.calc.post_execute()

        lt_rlzs = models.LtRealization.objects.filter(
            hazard_calculation=self.job.hazard_calculation.id)

        self.assertEqual(2, len(lt_rlzs))

        # Now we test that the htemp results were copied to the final location
        # in `hzrdr.hazard_curve` and `hzrdr.hazard_curve_data`.
        for rlz in lt_rlzs:
            # get hazard curves for this realization
            [pga_curves] = models.HazardCurve.objects.filter(
                lt_realization=rlz.id, imt='PGA')
            [sa_curves] = models.HazardCurve.objects.filter(
                lt_realization=rlz.id, imt='SA', sa_period=0.025)

            # In this calculation, we have 120 sites of interest.
            # We should have exactly that many curves per realization
            # per IMT.
            pga_curve_data = models.HazardCurveData.objects.filter(
                hazard_curve=pga_curves.id)
            self.assertEqual(120, len(pga_curve_data))
            sa_curve_data = models.HazardCurveData.objects.filter(
                hazard_curve=pga_curves.id)
            self.assertEqual(120, len(sa_curve_data))


class ImtsToNhlibTestCase(unittest.TestCase):
    """
    Tests for
    :func:`openquake.calculators.hazard.classical.core_next.im_dict_to_nhlib`.
    """

    def test_im_dict_to_nhlib(self):
        imts_in = {
            'PGA': [1, 2],
            'PGV': [2, 3],
            'PGD': [3, 4],
            'SA(0.1)': [0.1, 0.2],
            'SA(0.025)': [0.2, 0.3],
            'IA': [0.3, 0.4],
            'RSD': [0.4, 0.5],
            'MMI': [0.5, 0.6],
        }

        expected = {
            nhlib.imt.PGA(): [1, 2],
            nhlib.imt.PGV(): [2, 3],
            nhlib.imt.PGD(): [3, 4],
            nhlib.imt.SA(0.1, core_next.DEFAULT_SA_DAMPING): [0.1, 0.2],
            nhlib.imt.SA(0.025, core_next.DEFAULT_SA_DAMPING): [0.2, 0.3],
            nhlib.imt.IA(): [0.3, 0.4],
            nhlib.imt.RSD(): [0.4, 0.5],
            nhlib.imt.MMI(): [0.5, 0.6],
        }

        actual = core_next.im_dict_to_nhlib(imts_in)
        self.assertEqual(len(expected), len(actual))

        for i, (exp_imt, exp_imls) in enumerate(expected.items()):
            act_imls = actual[exp_imt]
            self.assertEqual(exp_imls, act_imls)


class HelpersTestCase(unittest.TestCase):
    """
    Tests for helper functions in the classical hazard calculator core module.
    """

    def test__exchange_and_conn_args(self):
        expected_conn_args = {
            'password': 'guest', 'hostname': 'localhost', 'userid': 'guest',
            'virtual_host': '/',
        }

        exchange, conn_args = core_next._exchange_and_conn_args()

        self.assertEqual('oq.htasks', exchange.name)
        self.assertEqual('direct', exchange.type)

        self.assertEqual(expected_conn_args, conn_args)

    @attr('slow')
    def test_get_site_collection_with_site_model(self):
        cfg = helpers.demo_file(
            'simple_fault_demo_hazard/job_with_site_model.ini')
        job = helpers.get_hazard_job(cfg)
        calc = core_next.ClassicalHazardCalculator(job)

        # Bootstrap the `site_data` table:
        calc.initialize_sources()
        calc.initialize_site_model()

        site_coll = core_next.get_site_collection(job.hazard_calculation)
        # Since we're using a pretty big site model, it's a bit excessive to
        # check each and every value.
        # Instead, we'll just test that the lenth of each site collection attr
        # is equal to the number of points of interest in the calculation.
        expected_len = len(job.hazard_calculation.points_to_compute())

        self.assertEqual(expected_len, len(site_coll))
        self.assertEqual(expected_len, len(site_coll.vs30))
        self.assertEqual(expected_len, len(site_coll.vs30measured))
        self.assertEqual(expected_len, len(site_coll.z1pt0))
        self.assertEqual(expected_len, len(site_coll.z2pt5))

    def test_get_site_collection_with_reference_parameters(self):
        cfg = helpers.demo_file(
            'simple_fault_demo_hazard/job.ini')
        job = helpers.get_hazard_job(cfg, username=getpass.getuser())
        calc = core_next.ClassicalHazardCalculator(job)

        site_coll = core_next.get_site_collection(job.hazard_calculation)

        # all of the parameters should be the same:
        self.assertTrue((site_coll.vs30 == 760).all())
        self.assertTrue((site_coll.vs30measured).all())
        self.assertTrue((site_coll.z1pt0 == 5).all())
        self.assertTrue((site_coll.z2pt5 == 100).all())

        # just for sanity, make sure the meshes are correct (the locations)
        job_mesh = job.hazard_calculation.points_to_compute()
        self.assertTrue((job_mesh.lons == site_coll.mesh.lons).all())
        self.assertTrue((job_mesh.lats == site_coll.mesh.lats).all())


class SignalTestCase(unittest.TestCase):

    def test_signal_task_complete(self):
        job_id = 7
        num_sources = 10

        def test_callback(body, message):
            self.assertEqual(dict(job_id=job_id, num_sources=num_sources),
                             body)
            message.ack()

        exchange, conn_args = core_next._exchange_and_conn_args()
        routing_key = core_next._ROUTING_KEY_FMT % dict(job_id=job_id)
        task_signal_queue = kombu.Queue(
            'htasks.job.%s' % job_id, exchange=exchange,
            routing_key=routing_key, durable=False, auto_delete=True)

        with kombu.BrokerConnection(**conn_args) as conn:
            task_signal_queue(conn.channel()).declare()
            with conn.Consumer(task_signal_queue,
                               callbacks=[test_callback]):

                # send the signal:
                core_next.signal_task_complete(job_id, num_sources)
                conn.drain_events()
