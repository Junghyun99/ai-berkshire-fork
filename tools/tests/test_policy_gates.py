"""Synthetic contract and adversarial input tests; no actual approval records."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from policy_validator import check_policy, check_proposal, evaluate_policy
from test_policy import example


class PolicyGateTests(unittest.TestCase):
    def assert_gate(self,p,gate):
        self.assertTrue(any(e.startswith(gate+':') for e in check_policy(p,as_of='2026-10-30')),gate)

    def test_all_twelve_gate_missing_field_mapping(self):
        fields={'G01':'portfolio_ids','G02':'policy_scope','G03':'objective','G04':'risk_capacity',
                'G05':'asset_rules','G06':'strategic_targets','G07':'risk_limits','G08':'benchmark',
                'G09':'approval_rules','G10':'provenance','G11':'validation_sources','G12':'feasibility_review'}
        for gate,field in fields.items():
            with self.subTest(gate=gate):
                p=example();del p[field];self.assert_gate(p,gate)

    def test_report_is_not_approval(self):
        r=evaluate_policy(example(),as_of='2026-10-30')
        self.assertEqual(r['result'],'PASS')
        self.assertEqual(len(r['gates']),12)
        self.assertFalse(r['approval_granted'])
        self.assertFalse(r['external_evidence_authenticated'])
        self.assertEqual(r['scope'],'mechanical_contract_only')

    def test_unknown_data_blocks(self):
        p=example();p['validation_sources']['prices']['status']='unknown'
        r=evaluate_policy(p,as_of='2026-10-30')
        self.assertEqual(r['gates']['G11']['status'],'UNKNOWN')
        self.assertEqual(r['result'],'BLOCKED')

    def test_asset_list_malformed_and_duplicate_no_crash(self):
        for value in ([{}],['equity','equity'],[' '],True):
            p=example();p['eligible_assets']=value;self.assert_gate(p,'G05')

    def test_ineligible_allocation(self):
        p=example();p['eligible_assets']=['cash'];self.assert_gate(p,'G06')

    def test_leverage_boolean_and_cap(self):
        for v in ('false',1,None):
            p=example();p['asset_rules']['leverage_allowed']=v;self.assert_gate(p,'G05')
        p=example();p['risk_limits']['gross_leverage_max']=2;self.assert_gate(p,'G05')

    def test_numeric_limits(self):
        for key in ('single_name_max_pct','sector_max_pct','liquidity_min_pct'):
            for value in (-1,101,True,'NaN','Infinity'):
                p=example();p['risk_limits'][key]=value;self.assert_gate(p,'G04')

    def test_benchmark_exception_needs_owner_and_evidence(self):
        p=example();p['benchmark']={'exception':True,'reason':'fixture exception','approved_by':'user1','evidence_ref':'fixture:exception'}
        self.assertEqual(check_policy(p,as_of='2026-10-30'),[])
        p['benchmark']['approved_by']='other';self.assert_gate(p,'G08')
        del p['benchmark']['evidence_ref'];self.assert_gate(p,'G08')

    def test_expired_future_and_reversed_dates(self):
        for changes in ({'effective_at':'2027-01-01'}, {'approved_at':'2027-01-01'},
                        {'effective_at':'2026-10-27'}, {'approved_at':'bad'},
                        {'expiry_rule':'fixed_date','expires_at':'2026-10-29'},
                        {'expiry_rule':'until_superseded','expires_at':'2027-01-01'}):
            p=example();p.update(changes);self.assert_gate(p,'G09')

    def test_basis_and_source_future_dates(self):
        p=example();p['risk_limits']['currency']='USD';self.assert_gate(p,'G07')
        p=example();p['risk_limits']['as_of']='2027-01-01';self.assert_gate(p,'G07')
        p=example();p['validation_sources']['fx']['as_of']='2027-01-01';self.assert_gate(p,'G11')

    def test_version_bound_records(self):
        p=example();p['provenance']['policy_version']='old';self.assert_gate(p,'G10')
        p=example();p['feasibility_review']['policy_version']='old';self.assert_gate(p,'G12')

    def test_human_review_is_not_agent_claim(self):
        for change in ({'actor_type':'agent'},{'unresolved_conflicts':['liquidity']},
                       {'reviewed_at':'2026-10-29'},{'evidence_ref':'TBD'}):
            p=example();p['feasibility_review'].update(change);self.assert_gate(p,'G12')

    def test_cashflow_explicit_empty_and_invalid(self):
        self.assertEqual(check_policy(example(),as_of='2026-10-30'),[])
        for value in ({},[{}],[{'type':'withdrawal','amount':True,'currency':'KRW','date':'2027-01-01'}]):
            p=example();p['cash_flow_needs']=value;self.assert_gate(p,'G03')

    def test_malformed_policy_proposal_no_attribute_error(self):
        for value in (None,[],True,'bad'):
            self.assertTrue(check_proposal(value,{},{}))
        p=example()
        for field in list(p):
            for value in (None,[],{},True):
                with self.subTest(field=field,value=value):
                    q=copy.deepcopy(p);q[field]=value
                    result=check_policy(q,as_of='2026-10-30')
                    if field in ("cash_flow_needs","prohibited_assets") and value == []:
                        self.assertEqual(result,[])
                    else:
                        self.assertTrue(result)

    def test_checks_do_not_mutate_policy(self):
        p=example();before=copy.deepcopy(p);evaluate_policy(p,as_of='2026-10-30')
        self.assertEqual(p,before)

    def test_cli_draft_exit_and_legacy_output_keys(self):
        p=example();p['status']='draft'
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'draft.json';path.write_text(json.dumps(p))
            proc=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'policy_validator.py'),'policy','--policy',str(path)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,2)
            result=json.loads(proc.stdout)
            self.assertEqual(result['result'],'BLOCKED')
            self.assertIsInstance(result['errors'],list)
            self.assertEqual(len(result['gates']),12)
