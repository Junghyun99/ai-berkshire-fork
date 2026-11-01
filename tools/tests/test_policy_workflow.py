"""CLI integration contract, not a Claude Skill runtime evaluation.

All policies and approvals below are synthetic fixtures in temporary storage.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_policy import example
from test_policy_registry import inputs

TOOLS = Path(__file__).resolve().parents[1]


class PolicyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.registry = self.root / 'registry'
        self.draft, self.event = inputs()
        self.portfolio = dict(snapshot_id='fixture-s1', policy_id='example',
                              policy_version='1.0', net_asset_value=1000, base_currency='KRW')
        self.proposal = dict(proposal_id='fixture-p1', portfolio_snapshot_id='fixture-s1',
                             policy_id='example', policy_version='1.0', proposed_weight=5,
                             weight_basis='total_portfolio', policy_checks={'fixture': 'pass'})

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return str(path)

    def run_cli(self, tool, *args):
        return subprocess.run([sys.executable, str(TOOLS / tool), *map(str, args)],
                              cwd=self.root, capture_output=True, text=True, timeout=15)

    def validate(self, policy, proposal=False):
        args = ['proposal' if proposal else 'policy', '--policy', self.write('policy.json', policy)]
        if proposal:
            args += ['--portfolio', self.write('portfolio.json', self.portfolio),
                     '--proposal', self.write('proposal.json', self.proposal)]
        result = self.run_cli('policy_validator.py', *args)
        return result.returncode, json.loads(result.stdout)

    def registration(self, research=False):
        args = ['register', '--registry', self.registry,
                '--policy', self.write('draft.json', self.draft),
                '--approval-event', self.write('event.json', self.event)]
        if research:
            args.append('--research-only')
        return self.run_cli('policy_registry.py', *args)

    def test_draft_does_not_become_active_after_validation(self):
        code, report = self.validate(self.draft, proposal=True)
        self.assertEqual(code, 2)
        self.assertFalse(report['approval_granted'])
        self.assertIn('G09: policy not active', report['errors'])
        self.assertEqual(json.loads((self.root/'policy.json').read_text())['status'], 'draft')
        self.assertFalse(self.registry.exists())

    def test_data_and_approval_requirements_coexist_in_output(self):
        self.draft.pop('validation_sources')
        code, report = self.validate(self.draft)
        self.assertEqual(code, 2)
        self.assertNotEqual(report['gates']['G11']['status'], 'PASS')
        self.assertTrue(report['gates']['G11']['reasons'])
        self.assertNotEqual(report['gates']['G09']['status'], 'PASS')
        self.assertFalse(report['approval_granted'])
        # Structured reasons support separate Skill headings; this does not test LLM rendering.

    def test_no_operational_registration_even_with_complete_event(self):
        result = self.registration()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('authenticated approval unavailable', result.stderr)
        self.assertFalse(self.registry.exists())

    def test_research_mode_missing_approval_blocked(self):
        self.event = {}
        result = self.registration(research=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('explicit user approval event required', result.stderr)
        self.assertFalse(self.registry.exists())

    def test_approval_version_mismatch_blocked(self):
        self.event['version'] = 'other'
        result = self.registration(research=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('approval policy/version mismatch', result.stderr)
        self.assertFalse(self.registry.exists())

    def test_research_register_show_audit_then_proposal_blocked(self):
        result = self.registration(research=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['approval_authenticated'])
        shown = self.run_cli('policy_registry.py', 'show', '--registry', self.registry)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        policy = json.loads(shown.stdout)
        self.assertEqual(policy['status'], 'research_active')
        audit = self.run_cli('policy_registry.py', 'audit', '--registry', self.registry)
        self.assertEqual(json.loads(audit.stdout)['projection_errors'], [])
        code, report = self.validate(policy, proposal=True)
        self.assertEqual(code, 2)
        self.assertIn('G09: policy not active', report['errors'])
        self.assertFalse(report['approval_granted'])

    def test_policy_version_mismatch_in_proposal(self):
        self.proposal['policy_version'] = 'other'
        code, report = self.validate(example(), proposal=True)
        self.assertEqual(code, 2)
        self.assertIn('P03: policy version mismatch', report['errors'])

    def test_snapshot_mismatch_in_proposal(self):
        self.proposal['portfolio_snapshot_id'] = 'other'
        code, report = self.validate(example(), proposal=True)
        self.assertEqual(code, 2)
        self.assertIn('P04: snapshot mismatch', report['errors'])

    def test_mechanical_pass_is_not_approval(self):
        code, report = self.validate(example(), proposal=True)
        self.assertEqual(code, 0)
        self.assertEqual(report['result'], 'PASS')
        self.assertEqual(report['scope'], 'mechanical_contract_only')
        self.assertFalse(report['approval_granted'])
        self.assertFalse(self.registry.exists())
