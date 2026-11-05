"""Fase 2: oráculos analíticos y pruebas de integración sin datos corporativos."""
import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from src.actuarial.liabilities import (annual_to_monthly_q, MortalityTable,
    synthetic_mortality, LiabilityAssumptions as LA, Beneficiary, value_individual)
from src.actuarial.eligibility import (calculate_isc, isc_data_quality,
    build_isc_cohorts, describe_isc_cohorts, isc_universe_summary)
from src.actuarial.pool import value_cohort, project_monthly_pool
from src.simulation.integrated import synthetic_participants, compare_cohorts
from src.utils.integrated_reporting import report_html


def table(q):
    return MortalityTable({(age,'*'):q for age in range(151)},synthetic=True)


def participants(capital=(10.,20.), ages=(60,80)):
    return pd.DataFrame(dict(registro=['PERSON_CANARY_001','PERSON_CANARY_002'],
        edad=ages,sexo=['F','M'],capital_mas_bono=capital,
        capital_necesario_sm=[100.,100.],prestacion_mensual=[1.,2.],riesgo=['VEJEZ']*2,
        private_name=['NAME_CANARY_A','NAME_CANARY_B']))


class MortalityTests(unittest.TestCase):
    def test_annual_monthly_survival_identity(self):
        for q in (0,.01,.2,.8,1):
            self.assertAlmostEqual((1-annual_to_monthly_q(q))**12,1-q,places=12)

    def test_invalid_probabilities(self):
        for q in (-.1,1.01,float('nan'),float('inf')):
            with self.subTest(q=q),self.assertRaises(ValueError): annual_to_monthly_q(q)

    def test_age_sex_period_and_missing_table(self):
        t=MortalityTable({(60,'F'):.1,(60,'M'):.2,(61,'F'):.3},period_factors=(1.,.5))
        self.assertEqual(t.annual_q(60,'M',0),.2)
        self.assertEqual(t.annual_q(61,'F',1),.15)
        with self.assertRaises(ValueError): t.annual_q(90,'F',0)
        with self.assertRaises(ValueError): t.annual_q(60,'F',2)
        with self.assertRaises(ValueError): MortalityTable({(60,'*'):2}).annual_q(60,'M',0)


class LiabilityTests(unittest.TestCase):
    def zero(self,months=12): return LA(horizon_months=months,annual_discount=0,annual_indexation=0)

    def test_zero_mortality_discount_and_rac(self):
        v=value_individual(60,'F',120,10,table(0),self.zero())
        self.assertEqual(v.present_value,120)
        self.assertEqual(v.rac,1)
        self.assertTrue(v.terminal_pending)

    def test_total_mortality_preserves_death_month_accrual(self):
        v=value_individual(60,'F',100,10,table(1),self.zero())
        np.testing.assert_allclose(v.flows.benefit_due,[10]+[0]*11)
        self.assertEqual(v.present_value,10)
        self.assertFalse(v.terminal_pending)

    def test_zero_vpa_is_not_infinite_coverage(self):
        v=value_individual(60,'F',100,0,table(0),self.zero())
        self.assertEqual(v.present_value,0)
        self.assertTrue(np.isnan(v.rac))
        self.assertFalse(v.terminal_pending)

    def test_closed_form_indexation_discount_and_expenses(self):
        a=LA(horizon_months=24,annual_discount=.06,annual_indexation=.04,expense_fraction=.1,expense_per_recipient_month=.5)
        expected=sum((10*1.04**((m-1)/12)*1.1+.5)/1.06**(m/12) for m in range(1,25))
        self.assertAlmostEqual(value_individual(60,'F',100,10,table(0),a).present_value,expected)

    def test_age_sex_benefit_horizon_and_mortality_sensitivity(self):
        a=self.zero()
        younger=value_individual(60,'F',100,10,synthetic_mortality(),a)
        older=value_individual(85,'F',100,10,synthetic_mortality(),a)
        self.assertLess(older.present_value,younger.present_value)
        self.assertAlmostEqual(value_individual(60,'F',100,20,synthetic_mortality(),a).present_value,2*younger.present_value)
        self.assertGreater(value_individual(60,'F',100,10,synthetic_mortality(),self.zero(24)).present_value,younger.present_value)
        differentiated=MortalityTable({(age,sex):q for age in range(151) for sex,q in [('F',.1),('M',.2)]})
        self.assertGreater(value_individual(60,'F',1,1,differentiated,a).present_value,value_individual(60,'M',1,1,differentiated,a).present_value)

    def test_beneficiary_continues_after_principal_death(self):
        b=Beneficiary(55,'F',.6,table(0))
        v=value_individual(65,'M',100,10,table(1),self.zero(3),b)
        np.testing.assert_allclose(v.flows.principal_benefit_due,[10,0,0])
        np.testing.assert_allclose(v.flows.beneficiary_benefit_due,[0,6,6])
        self.assertEqual(v.present_value,22)
        self.assertTrue(v.terminal_pending)

    def test_beneficiary_death_and_terminal_age_not_forced_death(self):
        b=Beneficiary(60,'F',1,table(1))
        v=value_individual(65,'M',10,1,table(1),self.zero(3),b)
        self.assertFalse(v.terminal_pending)
        terminal=LA(terminal_age=61,annual_discount=0,annual_indexation=0)
        v=value_individual(60,'F',10,1,table(0),terminal)
        self.assertEqual(len(v.flows),12)
        self.assertTrue(v.terminal_pending)

    def test_survival_bounds_and_continuity(self):
        v=value_individual(70,'M',100,1,synthetic_mortality(),self.zero(300))
        start,end=v.flows.principal_survival_start,v.flows.principal_survival_end
        self.assertTrue(start.between(0,1).all())
        self.assertTrue(end.between(0,1).all())
        np.testing.assert_allclose(start.iloc[1:],end.iloc[:-1])
        self.assertTrue((end <= start).all())

    def test_invalid_individual_parameters(self):
        for kw in (dict(capital=-1),dict(age=float('nan')),dict(monthly_benefit=-1),
                   dict(assumptions=LA(horizon_months=0)),dict(assumptions=LA(annual_discount=-1)),
                   dict(beneficiary=Beneficiary(50,'F',1.2,table(0)))):
            args=dict(age=60,sex='F',capital=1,monthly_benefit=1,mortality=table(0),assumptions=self.zero())
            args.update(kw)
            with self.subTest(kw=kw),self.assertRaises(ValueError): value_individual(**args)


class CohortAndPoolTests(unittest.TestCase):
    def test_heterogeneous_initial_capital_liability_and_horizon(self):
        frame=participants()
        a=LA(terminal_age=81,annual_discount=0,annual_indexation=0)
        v=value_cohort(frame,table(0),a)
        self.assertEqual(v.initial_capital,30)
        self.assertEqual(len(v.flows),252)
        self.assertEqual(v.initial_liability,252*3)
        self.assertAlmostEqual(v.initial_coverage,30/(252*3))
        self.assertTrue(v.terminal_pending)
        self.assertEqual(v.initial_liability,sum(x.present_value for x in v.individuals.values()))

    def test_accounting_and_continuity_in_all_regimes_with_negative_returns(self):
        v=value_cohort(participants(),table(.1),LA(horizon_months=36))
        for regime in ('no_support','guarantee','variable'):
            p=project_monthly_pool(v,-.12,regime).projection
            np.testing.assert_allclose(p.closing_assets,p.opening_assets+p.investment_income+p.external_support-p.benefits_paid-p.expenses_paid,atol=1e-12)
            np.testing.assert_allclose(p.opening_assets.iloc[1:],p.closing_assets.iloc[:-1])
            self.assertTrue((p.closing_assets >= 0).all())
            np.testing.assert_allclose(p.benefit_due,p.benefits_paid+p.unpaid_benefits)
            np.testing.assert_allclose(p.expense_due,p.expenses_paid+p.unpaid_expenses)
            np.testing.assert_allclose(p.cumulative_unpaid,(p.unpaid_benefits+p.unpaid_expenses).cumsum())
            np.testing.assert_allclose(p.pending_obligations,p.cumulative_unpaid+p.future_liability_in_horizon)

    def test_zero_capital_guarantee_and_unpaid(self):
        v=value_cohort(participants((0,0)),table(0),LA(horizon_months=2,annual_discount=0,annual_indexation=0,expense_fraction=.1))
        no=project_monthly_pool(v,0,'no_support')
        yes=project_monthly_pool(v,0,'guarantee')
        self.assertAlmostEqual(no.summary['unpaid_total'],6.6)
        self.assertAlmostEqual(yes.summary['external_support_total'],6.6)
        self.assertAlmostEqual(yes.summary['external_support_pv'],6.6)
        self.assertEqual(yes.summary['unpaid_total'],0)
        self.assertEqual(yes.summary['first_insufficiency_month'],1)
        np.testing.assert_allclose(yes.projection.benefits_paid,[3,3])
        np.testing.assert_allclose(yes.projection.benefits_funded_by_pool,[0,0])

    def test_analytical_reserve_and_support(self):
        f=participants((.5,0)).iloc[:1]
        v=value_cohort(f,table(0),LA(horizon_months=2,annual_discount=0,annual_indexation=0))
        result=project_monthly_pool(v,0,'guarantee')
        self.assertEqual(v.initial_liability,2)
        self.assertAlmostEqual(result.summary['external_support_pv'],1.5)
        np.testing.assert_allclose(result.projection.future_liability_in_horizon,[1,0])

    def test_no_shortfall_fully_funded_and_empty_cohort(self):
        v=value_cohort(participants((10000,10000)),table(0),LA(horizon_months=2))
        result=project_monthly_pool(v,0)
        self.assertIsNone(result.summary['first_insufficiency_month'])
        self.assertEqual(result.summary['unpaid_total'],0)
        empty=value_cohort(participants().iloc[:0],table(0),LA(horizon_months=2))
        self.assertEqual(empty.initial_capital,0)
        self.assertTrue(np.isnan(empty.initial_coverage))
        self.assertEqual(project_monthly_pool(empty).summary['participants'],0)

    def test_beneficiary_flows_reach_pool(self):
        f=participants((0,0)).iloc[:1]
        v=value_cohort(f,table(1),LA(horizon_months=3,annual_discount=0,annual_indexation=0),
            {f.registro.iloc[0]:Beneficiary(55,'F',.5,table(0))})
        p=project_monthly_pool(v,0,'guarantee').projection
        np.testing.assert_allclose(p.benefit_due,[1,.5,.5])
        np.testing.assert_allclose(p.external_support,[1,.5,.5])

    def test_bad_cohort_and_regime_rejected(self):
        frame=participants(); frame.loc[1,'registro']=frame.loc[0,'registro']
        with self.assertRaises(ValueError): value_cohort(frame,table(0))
        with self.assertRaises(ValueError): value_cohort(participants(),table(0),beneficiaries={'unknown':Beneficiary(50,'F',1,table(0))})
        v=value_cohort(participants(),table(0),LA(horizon_months=1))
        with self.assertRaises(ValueError): project_monthly_pool(v,-1)
        with self.assertRaises(ValueError): project_monthly_pool(v,regime='fake')


class ISCIntegrationTests(unittest.TestCase):
    def test_risk_normalization_quality_negative_and_unknown(self):
        f=participants((10,20))
        f=pd.concat([f]*4,ignore_index=True)
        f['riesgo']=['VEJEZ',' GPM ','sustitución-gpm','SUSTITUCIÓN — GPM',' VEJEZ ','DESCONOCIDO',None,'INVALIDEZ']
        f['capital_mas_bono']=[10,10,10,10,-1,10,'x',None]
        c=calculate_isc(f)
        self.assertEqual(c.isc_aplicable.tolist(),[True,False,False,False,True,False,False,True])
        self.assertEqual(c.riesgo_desconocido.sum(),1)
        self.assertTrue(c.capital_negativo.iloc[4])
        self.assertTrue(pd.isna(c.ISC.iloc[4]))
        self.assertTrue(pd.isna(c.descapitalizada_calc.iloc[4]))
        self.assertLess(c.ISC_bruto.iloc[4],0)
        self.assertEqual(isc_universe_summary(f).registros.sum(),len(f))
        self.assertEqual(isc_data_quality(c)['capital_negativo'],1)

    def test_zero_negative_missing_denominators(self):
        f=pd.concat([participants()]*2,ignore_index=True)
        f['capital_necesario_sm']=[0,-1,None,'x']
        self.assertTrue(calculate_isc(f).ISC.isna().all())

    def test_nested_cohorts_boundaries_and_no_duplicates(self):
        f=synthetic_participants()
        groups=build_isc_cohorts(f)
        previous=set()
        for name in 'ABCDE':
            keys=set(groups[name].registro)
            self.assertTrue(previous.issubset(keys)); previous=keys
            self.assertEqual(len(keys),len(groups[name]))
        self.assertFalse(set(groups['A'].registro)&set(groups['adicional'].registro))
        self.assertEqual(set(groups['E'].registro),set(groups['A'].registro)|set(groups['adicional'].registro))
        self.assertTrue((groups['A'].ISC < 1).all())
        self.assertFalse((groups['A'].capital_mas_bono < 0).any())
        stats=describe_isc_cohorts(groups)
        self.assertEqual(stats.query("cohort == 'A'").records.iloc[0],len(groups['A']))
        with self.assertRaises(ValueError): build_isc_cohorts(pd.concat([f,f]))

    def test_source_concordance_excludes_missing_and_invalid_classification(self):
        f=participants((-1,10)); f['descapitalizacion']=[101,np.nan]
        quality=isc_data_quality(calculate_isc(f))
        self.assertEqual(quality['clasificacion_comparable'],0)

    def test_custom_risk_catalog_requires_explicit_configuration(self):
        f=participants(); f['riesgo']='OTRO VALIDADO'
        self.assertFalse(calculate_isc(f).isc_aplicable.any())
        self.assertTrue(calculate_isc(f,known_risks=['OTRO VALIDADO']).isc_aplicable.all())
        f['riesgo']='GPM'
        self.assertFalse(calculate_isc(f,known_risks=['GPM']).isc_aplicable.any())


class PipelineTests(unittest.TestCase):
    def test_cohort_comparison_consistency_and_privacy(self):
        f=participants()
        summary,results=compare_cohorts(f,table(0),LA(horizon_months=3,annual_discount=0,annual_indexation=0))
        self.assertEqual(len(summary),18)
        for name in 'ABCDE':
            rows=summary.query('cohort == @name')
            self.assertEqual(rows.initial_capital.nunique(),1)
            self.assertEqual(rows.initial_liability.nunique(),1)
        a=dict(comparison=summary,sensitivity=summary,universe=isc_universe_summary(f),
            quality=isc_data_quality(calculate_isc(f)),parameters={'synthetic':True})
        # Even if caller attaches individual columns, the report ignores them.
        a['comparison']['private_name']='PRIVATE_COLUMN_CANARY'
        a['individuals']=f
        for technical in (False,True):
            report=report_html(a,{},technical)
            for secret in ('PERSON_CANARY','NAME_CANARY','PRIVATE_COLUMN_CANARY'):
                self.assertNotIn(secret,report)
            self.assertIn('DATOS SINTÉTICOS',report)
            self.assertIn('valoración terminal pendiente',report)

    def test_programmed_withdrawal_is_explicitly_pending(self):
        from src.actuarial.programmed_withdrawal import project_programmed_withdrawal
        with self.assertRaises(NotImplementedError): project_programmed_withdrawal()


class SensitivityAndExportTests(unittest.TestCase):
    def test_sensitivity_keeps_composition_and_changes_only_assumptions(self):
        f=participants((1,2))
        a=LA(horizon_months=24,annual_discount=.03,annual_indexation=.02,expense_fraction=.03)
        base=value_cohort(f,synthetic_mortality(),a)
        higher_index=value_cohort(f,synthetic_mortality(),replace(a,annual_indexation=.05))
        higher_expense=value_cohort(f,synthetic_mortality(),replace(a,expense_fraction=.08))
        longer_lived=value_cohort(f,synthetic_mortality(.7),a)
        for v in (higher_index,higher_expense,longer_lived):
            self.assertEqual(v.initial_capital,base.initial_capital)
            self.assertGreater(v.initial_liability,base.initial_liability)
        high=project_monthly_pool(base,.1,'guarantee')
        low=project_monthly_pool(base,-.1,'guarantee')
        self.assertEqual(high.summary['initial_liability'],low.summary['initial_liability'])
        self.assertGreater(low.summary['external_support_pv'],high.summary['external_support_pv'])

    def test_integrated_artifacts_are_aggregate_and_self_contained(self):
        import tempfile
        import struct
        import json
        from pathlib import Path
        from unittest.mock import patch
        from src.simulation.integrated import generate_integrated
        f=participants()
        summary,results=compare_cohorts(f,table(0),LA(horizon_months=3,annual_discount=0,annual_indexation=0))
        summary['scenario']='base'
        analysis=dict(comparison=summary,results=results,sensitivity=summary,
            universe=isc_universe_summary(f),quality=isc_data_quality(calculate_isc(f)),
            cohort_statistics=describe_isc_cohorts(build_isc_cohorts(f)),parameters={'synthetic':True})
        with tempfile.TemporaryDirectory() as directory:
            with patch('src.simulation.integrated.run_analysis',return_value=analysis):
                output=generate_integrated(Path(directory))
            pngs=list((output/'powerpoint').glob('*.png'))
            self.assertEqual(len(pngs),7)
            self.assertEqual(len(list((output/'powerpoint').glob('*.svg'))),7)
            self.assertTrue(all(struct.unpack('>II',p.read_bytes()[16:24])==(4000,2250) for p in pngs))
            for file in output.rglob('*'):
                if file.suffix in ('.html','.csv','.json','.svg'):
                    content=file.read_text(encoding='utf-8')
                    for secret in ('PERSON_CANARY','NAME_CANARY','private_name'):
                        self.assertNotIn(secret,content)
            executive=(output/'executive.html').read_text(encoding='utf-8')
            self.assertIn('data:image/svg+xml;base64,',executive)
            self.assertNotIn('<script src=',executive)
            self.assertTrue((output/'technical/report.html').is_file())
            parameters=json.loads((output/'technical/parameters.json').read_text(encoding='utf-8'))
            self.assertIn('source_sha256',parameters['reproducibility'])
