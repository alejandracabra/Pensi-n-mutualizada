"""Fase 3: toda entrada es sintética; nunca se leen bases corporativas."""
from dataclasses import replace
from pathlib import Path
import hashlib
import tempfile
import unittest
import warnings
import numpy as np
import pandas as pd
from src.data.risk_catalog import RiskCatalog,DEFAULT_CATALOG,load_local_yaml
from src.data.schema import DataMapping,ActuarialConfiguration
from src.data.adapter import adapt_frame,read_local_source
from src.data.validation import validate_adapted
from src.data.mortality import mortality_from_frame
from src.actuarial.liabilities import (LiabilityAssumptions as LA, synthetic_mortality,
    Beneficiary, MortalityTable, value_individual)
from src.actuarial.eligibility import (calculate_isc,isc_data_quality,isc_universe_summary,
    build_isc_cohorts,calculate_eligibility_scenarios,reconcile_isc,compare_historical_counts,eligibility_figures)
from src.actuarial.pool import value_cohort,project_monthly_pool
from src.simulation.validated import simulate_adapted,IncompleteCohortError
from src.simulation.adaptation_demo import demo_data,run_demo
from src.utils.disclosure import DisclosurePolicy,disclosure_decision
from src.utils.integrated_reporting import validated_report,report_html


def complete(n=6):
    return pd.DataFrame(dict(registro=[f'PRIVATE_CANARY_{i}' for i in range(n)],
        edad=[65]*n,sexo=['F']*n,riesgo=['VEJEZ']*n,capital_mas_bono=[40.]*n,
        capital_necesario_sm=[100.]*n,prestacion_mensual=[1.]*n,
        beneficiarios_estado=['none_confirmed']*n,
        nombre=['NAME_CANARY']*n))


def mapping(**kwargs):
    options=dict(valuation_date='2026-11-05',prices_date='2026-11-05',source_currency='ABSTRACT',
        model_currency='ABSTRACT',observation_unit='pensionado')
    options.update(kwargs)
    return DataMapping(**options)


def actuarial(**kwargs):
    options=dict(mortality=synthetic_mortality(),assumptions=LA(horizon_months=24),annual_return=.02,
        authorized_for_scenario=True,allow_provisional_catalog=True)
    options.update(kwargs)
    return ActuarialConfiguration(**options)


def adapt(frame=None,**kwargs):
    return adapt_frame(complete() if frame is None else frame,kwargs.get('mapping',mapping()),
        kwargs.get('catalog',DEFAULT_CATALOG),kwargs.get('actuarial',actuarial()))


class RiskCatalogTests(unittest.TestCase):
    def test_explicit_aliases_and_mandatory_exclusions(self):
        c=RiskCatalog((('VEJEZ',True),('NUEVA',True)),(('VARIANTE', 'NUEVA'),))
        f=complete(6); f['riesgo']=['VEJEZ','variante','sustitución—gpm','GPM','OTRA',None]
        classified=calculate_isc(f,catalog=c)
        self.assertEqual(classified.isc_aplicable.tolist(),[True,True,False,False,False,False])
        self.assertEqual(classified.riesgo_normalizado.iloc[1],'NUEVA')
        rec=reconcile_isc(classified).set_index('indicator').records
        self.assertEqual(rec['excluded_by_rule'],2)
        self.assertEqual(rec['unknown_risk'],1)
        self.assertEqual(rec['missing_risk'],1)

    def test_configuration_persists_across_all_isc_consumers(self):
        c=RiskCatalog((('NUEVA',True),))
        f=complete(); f['riesgo']='NUEVA'
        classified=calculate_isc(f,catalog=c)
        self.assertEqual(isc_data_quality(classified)['isc_aplicable'],6)
        self.assertEqual(isc_universe_summary(classified).registros.sum(),6)
        self.assertEqual(isc_universe_summary(classified).registros.iloc[2],6)
        groups=build_isc_cohorts(classified)
        self.assertEqual(len(groups['A']),6)
        scenarios=calculate_eligibility_scenarios(classified)
        self.assertEqual(scenarios.N_candidatos.tolist(),[6]*5)
        figures=eligibility_figures(scenarios)
        self.assertEqual(list(figures['isc_escenarios_registros'].data[0].y),[6]*5)
        with self.assertRaises(ValueError): isc_data_quality(classified,catalog=DEFAULT_CATALOG)
        # Explicit reclassification is permitted and is never done behind a caller's back.
        self.assertEqual(isc_data_quality(calculate_isc(classified,catalog=DEFAULT_CATALOG))['isc_aplicable'],0)

    def test_invalid_aliases_or_exclusions_are_rejected(self):
        for categories,aliases in [((('GPM',True),),()),((('VEJEZ',True),),(('GPM','VEJEZ'),)),
            ((('VEJEZ',True),),(('X','NOT_CONFIGURED'),))]:
            with self.subTest(categories=categories),self.assertRaises(ValueError): RiskCatalog(categories,aliases)

    def test_example_yaml_and_local_config(self):
        root=Path(__file__).resolve().parents[1]
        c=RiskCatalog.load(root/'config/risk_catalog.example.yaml')
        self.assertTrue(c.provisional)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'risk.local.yaml'
            p.write_text('provisional: false\nversion: test\ncategories:\n  EJEMPLO: true\n',encoding='utf-8')
            self.assertEqual(RiskCatalog.load(p).classify('ejemplo')[1],'applicable')
        with self.assertRaises(ValueError): load_local_yaml(root/'config/corporate.local.yaml')

    def test_historical_counts_are_only_comparison_not_targets(self):
        f=calculate_isc(complete())
        before=f.copy(deep=True)
        differences=compare_historical_counts(f,{'total':100,'applicable':30})
        self.assertTrue(differences.alert.all())
        pd.testing.assert_frame_equal(f,before)
        self.assertEqual(differences.observed.tolist(),[6,6])


class AdapterTests(unittest.TestCase):
    def test_mapping_alternatives_and_source_unchanged(self):
        source=complete().rename(columns={'edad':'Years','capital_mas_bono':'Capital +Bono'})
        original=source.copy(deep=True)
        d=adapt(source,mapping=mapping(columns=(('Years','edad'),)))
        pd.testing.assert_frame_equal(source,original)
        self.assertTrue(validate_adapted(d).ready_mask.all())
        self.assertNotIn('nombre',d.frame)
        self.assertGreater(len(d.transformations),3)

    def test_missing_actuarial_fields_do_not_block_descriptive_isc(self):
        f=complete().drop(columns=['edad','sexo','prestacion_mensual','registro','beneficiarios_estado'])
        d=adapt(f); diagnosis=validate_adapted(d)
        self.assertEqual(diagnosis.indicators['isc_calculable'],6)
        self.assertEqual(diagnosis.indicators['ready'],0)
        self.assertIn('edad',d.missing_columns)
        self.assertTrue(diagnosis.causes.identification.all())

    def test_missing_isc_field_is_diagnosed_without_fabrication(self):
        f=complete().drop(columns='capital_necesario_sm')
        d=adapt(f)
        self.assertTrue(d.frame.ISC.isna().all())
        self.assertEqual(validate_adapted(d).indicators['minimum_schema'],0)

    def test_duplicate_headers_and_collisions(self):
        f=complete(); f.columns=['same']*len(f.columns)
        with self.assertRaises(ValueError): adapt(f)
        f=complete(); f[' Edad ']=f.edad
        with self.assertRaises(ValueError): adapt(f)
        with self.assertRaises(ValueError): DataMapping(columns=(('A','edad'),('B','edad')))

    def test_non_numeric_negative_infinite_and_out_of_domain(self):
        f=complete(); f.loc[0,'capital_mas_bono']='no-numérico'
        f.loc[1,'capital_mas_bono']=-1; f.loc[2,'capital_mas_bono']=np.inf
        f.loc[3,'edad']=151
        d=adapt(f); diagnosis=validate_adapted(d)
        self.assertEqual(int(diagnosis.causes.capital.sum()),3)
        self.assertTrue(diagnosis.causes.age.iloc[3])
        self.assertTrue(d.frame.ISC.iloc[:3].isna().all())

    def test_duplicate_identifiers_never_deduplicated(self):
        f=complete(); f.loc[1,'registro']=f.loc[0,'registro']
        d=adapt(f); diagnosis=validate_adapted(d)
        self.assertEqual(len(d.frame),6)
        self.assertEqual(diagnosis.indicators['identification_pending'],2)
        with self.assertRaises(IncompleteCohortError): simulate_adapted(d)

    def test_sex_missing_and_explicit_unisex_hypothesis(self):
        f=complete(); f.loc[0,'sexo']=None
        self.assertTrue(validate_adapted(adapt(f)).causes.sex.iloc[0])
        d=adapt(f,mapping=mapping(allow_unisex=True))
        self.assertEqual(d.frame.sexo.iloc[0],'*')
        self.assertTrue(validate_adapted(d).ready_mask.all())
        self.assertTrue(d.frame.sexo_original.isna().iloc[0])

    def test_benefit_modes_no_automatic_smmlv(self):
        f=complete(); f['mesada']=5
        current=adapt(f,mapping=mapping(benefit_mode='current'))
        self.assertTrue(current.frame.prestacion_mensual.eq(5).all())
        undefined=adapt(f,mapping=mapping(benefit_mode='smmlv'))
        self.assertTrue(validate_adapted(undefined).causes.benefit.all())
        explicit=adapt(f,mapping=mapping(benefit_mode='smmlv',benefit_value=2,benefit_date='2026-11-05'))
        self.assertTrue(validate_adapted(explicit).ready_mask.all())
        wrong=adapt(f,mapping=mapping(benefit_mode='explicit',benefit_value=2,benefit_date='2025-11-05'))
        self.assertTrue(validate_adapted(wrong).causes.benefit.all())

    def test_currency_prices_and_date_fail_closed(self):
        f=complete(); f['moneda']='USD'
        self.assertTrue(validate_adapted(adapt(f)).causes.currency.all())
        f=complete(); f['fecha_corte']='2020-01-01'
        self.assertTrue(validate_adapted(adapt(f)).causes.date.all())
        f=complete(); f['fecha_precios']='bad-date'
        self.assertTrue(validate_adapted(adapt(f)).causes.date.all())
        self.assertTrue(validate_adapted(adapt(mapping=mapping(source_currency=None))).causes.currency.all())

    def test_explicit_money_scale_logged(self):
        d=adapt(mapping=mapping(amount_multiplier=1000))
        self.assertEqual(d.frame.capital_mas_bono.iloc[0],40000)
        self.assertEqual(d.frame.ISC.iloc[0],.4)
        self.assertIn('units',d.transformations.transformation.tolist())

    def test_read_only_workbook_and_duplicate_excel_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'synthetic.xlsx'
            complete().drop(columns='nombre').to_excel(p,index=False)
            before=hashlib.sha256(p.read_bytes()).hexdigest()
            d=read_local_source(p,mapping(),DEFAULT_CATALOG,actuarial())
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),before)
            self.assertEqual(len(d.frame),6)
            import openpyxl
            book=openpyxl.Workbook(); sheet=book.active
            sheet.append(['Edad','Edad']); sheet.append([65,66]); book.save(p); book.close()
            with self.assertRaises(ValueError): read_local_source(p,mapping(),DEFAULT_CATALOG)

    def test_mapping_example_loads(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(DataMapping.load(root/'config/data_mapping.example.yaml').source_currency,'ABSTRACT')


class ReadinessAndIntegrationTests(unittest.TestCase):
    def test_demo_cause_overlap_state_partition_and_stage_reconciliation(self):
        with warnings.catch_warnings(record=True) as caught:
            d,s,blocked=run_demo()
        self.assertTrue(blocked)
        self.assertTrue(caught)
        self.assertEqual(d.by_state.records.sum(),16)
        self.assertEqual(d.indicators['minimum_schema'],14)
        self.assertEqual(d.indicators['isc_calculable'],14)
        self.assertEqual(d.indicators['ready'],3)
        self.assertEqual(d.indicators['simulated'],3)
        self.assertEqual(s.reconciliation.selected.iloc[0],12)
        self.assertEqual(s.reconciliation.valued.iloc[0],3)
        self.assertEqual(s.reconciliation.simulated.iloc[0],3)
        self.assertEqual(s.reconciliation.excluded_pct_selected.iloc[0],75)
        self.assertEqual(s.monthly.summary['initial_capital'],120)
        self.assertEqual(d.indicators['cohort_records']['A'],12)

    def test_blocking_error_is_aggregate_and_default_never_partial(self):
        with self.assertRaises(IncompleteCohortError) as caught: simulate_adapted(demo_data())
        self.assertNotIn('SYN-',str(caught.exception))
        self.assertEqual(caught.exception.reconciliation.simulated.iloc[0],0)
        self.assertTrue(caught.exception.by_cause.records.sum()>0)

    def test_ready_and_nested_cohorts_simulate_without_skips(self):
        d=adapt()
        expected_vpa=sum(value_individual(65,'F',40,1,d.actuarial.mortality,d.actuarial.assumptions).present_value for _ in range(6))
        for cohort in 'ABCDE':
            s=simulate_adapted(d,cohort=cohort)
            self.assertEqual(s.monthly.summary['participants'],6)
            self.assertEqual(s.monthly.summary['initial_capital'],240)
            self.assertAlmostEqual(s.monthly.summary['initial_liability'],expected_vpa)
            self.assertEqual(s.reconciliation.pending.iloc[0],0)

    def test_all_beneficiary_information_states(self):
        f=complete(); f['beneficiarios']=None
        f.loc[0,'beneficiarios_estado']='unavailable'
        f.loc[1,'beneficiarios_estado']='unsupported'
        f.loc[2,'beneficiarios_estado']='known'
        f.at[2,'beneficiarios']=Beneficiary(60,'M',.5,synthetic_mortality())
        f.loc[3,'beneficiarios_estado']='known'
        d=validate_adapted(adapt(f))
        self.assertEqual(d.causes.beneficiaries.tolist(),[True,True,False,True,False,False])
        self.assertEqual(d.indicators['ready'],3)

    def test_mutating_data_invalidates_previous_readiness(self):
        d=adapt(); self.assertTrue(validate_adapted(d).ready_mask.all())
        d.frame.loc[0,'edad']=None
        with self.assertRaises(IncompleteCohortError): simulate_adapted(d)

    def test_missing_hypotheses_and_provisional_catalog_require_opt_in(self):
        self.assertEqual(validate_adapted(adapt(actuarial=ActuarialConfiguration())).indicators['ready'],0)
        self.assertTrue(validate_adapted(adapt(actuarial=actuarial(allow_provisional_catalog=False))).causes.risk_pending.all())
        self.assertTrue(validate_adapted(adapt(actuarial=actuarial(mortality=None))).causes.mortality.all())

    def test_unknown_unit_is_not_silently_one_person(self):
        d=validate_adapted(adapt(mapping=mapping(observation_unit='cuenta')))
        self.assertEqual(d.indicators['identification_pending'],6)


class ExternalMortalityAndFinanceTests(unittest.TestCase):
    def mortality(self,**kwargs):
        f=pd.DataFrame(dict(age=[65,66],sex=['*','*'],period=[2026,2027],annual_q=[.01,.02],improvement_factor=[1.,.9]))
        args=dict(valuation_year=2026,source='synthetic',version='v1',valid_from='2026-01-01',valid_to='2026-12-31',synthetic=True)
        args.update(kwargs)
        return mortality_from_frame(f,**args)

    def test_period_metadata_and_no_extrapolation(self):
        t=self.mortality()
        self.assertEqual(t.annual_q(65,'F',0),.01)
        self.assertAlmostEqual(t.annual_q(66,'M',1),.018)
        with self.assertRaises(ValueError): t.annual_q(67,'F',2)
        d=validate_adapted(adapt(actuarial=actuarial(mortality=t)))
        self.assertFalse(d.causes.mortality.any())  # ages 65/66 and periods 2026/2027 cover 24 months
        extended=validate_adapted(adapt(actuarial=actuarial(mortality=t,assumptions=LA(horizon_months=36))))
        self.assertTrue(extended.causes.mortality.all())  # age 67 / 2028 is missing, never extrapolated

    def test_expired_mortality_metadata_is_not_accepted(self):
        t=self.mortality(valid_from='2025-01-01',valid_to='2025-12-31')
        self.assertTrue(validate_adapted(adapt(actuarial=actuarial(mortality=t))).causes.mortality.all())

    def test_invalid_or_duplicate_external_rates(self):
        f=pd.DataFrame(dict(age=[65,65],sex=['F','F'],period=[2026,2026],annual_q=[.1,.1]))
        with self.assertRaises(ValueError): mortality_from_frame(f,valuation_year=2026,source='x',version='v1',valid_from='2026-01-01',valid_to='2026-12-31')
        with self.assertRaises(ValueError): self.mortality(source='')

    def test_discount_and_return_are_independent_and_reproducible(self):
        f=complete(2)
        a=LA(horizon_months=120,annual_discount=.03,annual_indexation=.02)
        low=value_cohort(f,synthetic_mortality(),a)
        high=value_cohort(f,synthetic_mortality(),replace(a,annual_discount=.08))
        self.assertLess(high.initial_liability,low.initial_liability)
        p=project_monthly_pool(low,-.1,'guarantee')
        q=project_monthly_pool(low,.1,'guarantee')
        self.assertEqual(p.summary['initial_liability'],q.summary['initial_liability'])
        self.assertNotEqual(p.summary['external_support_total'],q.summary['external_support_total'])
        self.assertNotAlmostEqual(p.summary['initial_funding_gap'],p.summary['external_support_total'])
        pd.testing.assert_frame_equal(p.projection,project_monthly_pool(low,-.1,'guarantee').projection)

    def test_tail_remains_unknown_not_zero(self):
        s=simulate_adapted(adapt())
        self.assertTrue(s.monthly.summary['terminal_pending'])
        self.assertTrue(np.isnan(s.monthly.summary['obligations_after_horizon_vpa']))
        self.assertGreater(s.monthly.summary['remaining_expected_survivors'],0)
        self.assertIn('truncado',s.monthly.summary['terminal_diagnosis'])


class DisclosureAndExecutiveTests(unittest.TestCase):
    def test_small_cells_and_complementary_differences_block_whole_bundle(self):
        p=DisclosurePolicy(10,True)
        self.assertFalse(disclosure_decision(100,[100,50],dict(A=50,B=51,C=70,D=80,E=90),p)[0])
        self.assertFalse(disclosure_decision(100,[95],dict(A=40,B=60,C=80,D=100,E=100),p)[0])
        self.assertTrue(disclosure_decision(100,[50],dict(A=20,B=40,C=60,D=80,E=100),p)[0])
        self.assertFalse(disclosure_decision(100,[50],{},DisclosurePolicy())[0])

    def test_report_default_blocks_and_never_serializes_identifiers(self):
        s=simulate_adapted(adapt())
        page=validated_report(s,DisclosurePolicy())
        self.assertIn('bloqueada',page)
        self.assertNotIn('PRIVATE_CANARY',page)
        self.assertNotIn('NAME_CANARY',page)
        # Even explicit approval does not bypass small-cell suppression.
        self.assertIn('suprimido',validated_report(s,DisclosurePolicy(10,True)))
        self.assertIn('bloqueada',report_html({'parameters':{'synthetic':False}},{}))

    def test_executive_one_row_per_cohort_and_technical_preserves_regimes(self):
        from src.simulation.integrated import compare_cohorts
        d=adapt(); summary,results=compare_cohorts(d.frame,d.actuarial.mortality,d.actuarial.assumptions)
        a=dict(comparison=summary,sensitivity=summary,parameters={'synthetic':True},
            universe=isc_universe_summary(d.frame),quality=isc_data_quality(d.frame))
        executive=report_html(a,{})
        technical=report_html(a,{},True)
        # Extract only the comparison table to avoid counting earlier universe tables.
        part=executive.split('6. Comparación de cohortes')[1].split('7. Sensibilidades')[0]
        self.assertEqual(part.count('<tr'),7)  # header + six cohorts
        self.assertNotIn('<td>guarantee</td>',executive)
        self.assertIn('<td>guarantee</td>',technical)
        self.assertIn('8. Limitaciones',executive)


class AuditEdgeCases(unittest.TestCase):
    def test_none_confirmed_cannot_hide_supplied_family_structure(self):
        f=complete(); f['beneficiarios']=None
        f.at[0,'beneficiarios']=[{'synthetic':True}]
        self.assertTrue(validate_adapted(adapt(f)).causes.beneficiaries.iloc[0])

    def test_multiple_causes_are_not_lost_in_primary_state(self):
        f=complete(); f.loc[0,'registro']=None; f.loc[0,'edad']=None; f.loc[0,'sexo']=None
        d=validate_adapted(adapt(f))
        self.assertTrue(d.causes.loc[0,['identification','age','sex']].all())
        self.assertEqual(d.states.iloc[0],'Identificación/unidad pendiente')
        self.assertEqual(d.by_state.records.sum(),len(f))

    def test_explicit_beneficiary_reaches_validated_model(self):
        f=complete(1); f['beneficiarios']=None; f['beneficiarios_estado']='known'
        zero=MortalityTable({(a,'*'):0 for a in range(151)},synthetic=True)
        dead=MortalityTable({(a,'*'):1 for a in range(151)},synthetic=True)
        f.at[0,'beneficiarios']=Beneficiary(60,'M',.5,zero)
        d=adapt(f,actuarial=actuarial(mortality=dead,assumptions=LA(horizon_months=3,annual_discount=0,annual_indexation=0)))
        s=simulate_adapted(d,regime='guarantee')
        np.testing.assert_allclose(s.monthly.projection.benefit_due,[1,.5,.5])
        self.assertTrue(s.monthly.summary['terminal_pending'])

    def test_source_isc_without_age_and_provisional_catalog_not_implicit_authorization(self):
        d=adapt(complete().drop(columns='edad'),actuarial=ActuarialConfiguration())
        self.assertTrue(d.frame.ISC.notna().all())
        self.assertEqual(validate_adapted(d).indicators['ready'],0)

    def test_new_output_guard_rejects_raw_data_paths(self):
        from src.utils.disclosure import require_safe_output
        root=Path(__file__).resolve().parents[1]
        with self.assertRaises(ValueError): require_safe_output(root/'data/raw/not_allowed')
        with self.assertRaises(ValueError): require_safe_output(root/'reports/outputs/../../data/raw/not_allowed')
