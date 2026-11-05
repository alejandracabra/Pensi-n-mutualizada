"""Pruebas independientes de datos corporativos."""
import unittest
import numpy as np
import pandas as pd
from src.actuarial.pool import (project_pool, DemographicParameters as D,
    FinancialParameters as F, ActuarialParameters as A)
from src.actuarial.eligibility import (calculate_isc, calculate_eligibility_scenarios,
    isc_universe_summary, isc_data_quality)

class PoolTests(unittest.TestCase):
    def test_financial_identity_and_cohort(self):
        p = project_pool()
        np.testing.assert_allclose(p.closing_assets, p.opening_assets + p.investment_income - p.benefits_paid - p.expenses_paid, atol=1e-10)
        np.testing.assert_allclose(p.closing_members, p.opening_members-p.expected_deaths)
        np.testing.assert_allclose(p.opening_assets.iloc[1:], p.closing_assets.iloc[:-1])
        np.testing.assert_allclose(p.opening_members.iloc[1:], p.closing_members.iloc[:-1])
        self.assertTrue((p.closing_assets >= 0).all())
        self.assertTrue((p.closing_members.diff().dropna() <= 0).all())

    def test_hand_calculated_cashflow(self):
        p = project_pool(D(10,65), F(100,0.1,0.1,0), A(10,(0.2,)))
        row=p.iloc[0]
        self.assertAlmostEqual(row.closing_members,8)
        self.assertAlmostEqual(row.investment_income,100)
        self.assertAlmostEqual(row.expenses_paid,110)
        self.assertAlmostEqual(row.benefits_paid,80)
        self.assertAlmostEqual(row.closing_assets,910)

    def test_no_mortality_no_return(self):
        p=project_pool(D(2,65),F(10,0,0,0),A(4,(0,0,0,0)))
        np.testing.assert_allclose(p.closing_assets,[12,4,0,0])
        np.testing.assert_allclose(p.unpaid_benefits,[0,0,4,8])

    def test_deaths_do_not_create_or_withdraw_money(self):
        p=project_pool(D(10,65),F(100,0,0,0),A(8,(1,0)))
        np.testing.assert_allclose(p.closing_members,[0,0])
        np.testing.assert_allclose(p.closing_assets,[1000,1000])
        np.testing.assert_allclose(p.benefits_paid,[0,0])

    def test_indexation_and_zero_capital(self):
        p=project_pool(D(1,65),F(100,0,0,0.1),A(10,(0,0)))
        np.testing.assert_allclose(p.benefit_due,[10,11])
        z=project_pool(D(1,65),F(0,0,0,0),A(10,(0,)))
        self.assertEqual(z.iloc[0].unpaid_benefits,10)

    def test_invalid_parameters(self):
        for args in [(D(0),F(),A()),(D(),F(annual_return=-1),A()),
                     (D(),F(capital_per_member=float('nan')),A()),
                     (D(),F(),A(8,(1.1,))), (D(),F(),A(8,()))]:
            with self.subTest(args=args), self.assertRaises(ValueError): project_pool(*args)

class ISCPilotTests(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame(dict(capital_mas_bono=[0,99,100,105,120,50,50,50],
            capital_necesario_sm=[100,100,100,100,100,100,0,100],edad=[65]*8,
            riesgo=['VEJEZ']*5+['GPM','VEJEZ',None]))

    def test_boundaries_and_exhaustive_partition(self):
        f=calculate_isc(self.fixture())
        self.assertEqual(f.descapitalizada_calc.iloc[:5].tolist(),[True,True,False,False,False])
        self.assertTrue(f.descapitalizada_calc.iloc[5:].isna().all())
        summary=isc_universe_summary(self.fixture())
        self.assertEqual(summary.registros.tolist(),[2,1,2,3])
        self.assertEqual(summary.registros.sum(),len(f))
        s=calculate_eligibility_scenarios(f,[1,1.05,1.2])
        self.assertEqual(s.N_candidatos.tolist(),[2,3,4])
        np.testing.assert_allclose(s.Brecha_capital_requerido,s.Capital_SM_requerido-s.Capital_mas_bono_total)

    def test_missing_source_flag_not_compared(self):
        f=self.fixture(); f['descapitalizacion']=np.nan
        self.assertEqual(isc_data_quality(calculate_isc(f))['clasificacion_comparable'],0)


class PresentationRegressionTests(unittest.TestCase):
    def test_pilot_exports_separate_artifacts(self):
        import tempfile
        import json
        from pathlib import Path
        from src.simulation.pilot import generate_pilot
        with tempfile.TemporaryDirectory() as directory:
            out=generate_pilot(Path(directory))
            parameters=json.loads((out/'technical/parameters.json').read_text())
            self.assertTrue(parameters['synthetic'])
            self.assertEqual(len(list((out/'powerpoint').glob('*.png'))),4)
            self.assertEqual(len(list((out/'powerpoint').glob('*.svg'))),4)
            flows=pd.read_csv(out/'technical/flows.csv')
            self.assertEqual(len(flows),len(parameters['actuarial']['annual_death_probabilities']))
            np.testing.assert_allclose(flows.closing_assets,flows.opening_assets+flows.investment_income-flows.benefits_paid-flows.expenses_paid,atol=1e-9)

    def test_capital_labels_have_exactly_one_unit_conversion(self):
        import matplotlib.pyplot as plt
        from src.visualization.executive import _capital_scenarios_chart
        frame=pd.DataFrame(dict(capital_mas_bono=[1e12],capital_necesario_sm=[2e12],edad=[65],riesgo=['VEJEZ']))
        chart,_=_capital_scenarios_chart(frame,'synthetic','no informado','no disponible')
        labels=[t.get_text() for t in chart.figure.axes[0].texts]
        self.assertIn('1,0',labels)
        self.assertIn('2,0',labels)
        self.assertNotIn('supera',chart.figure._suptitle.get_text())
        plt.close(chart.figure)
