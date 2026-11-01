import copy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_cashflow import calculate


def sample(method='twr'):
    daily = method == 'mwr'
    return {'schema_version': 'cashflow-core-0.1', 'method': method,
            'currency': 'KRW', 'scope_id': 'synthetic', 'source_ref': 'fixture',
            'quality': 'synthetic_fixture', 'date_basis': 'Asia/Seoul calendar dates',
            'start': {'at': '2025-01-01' if daily else '2025-01-01T00:00:00Z', 'nav': '100'},
            'end': {'at': '2026-01-01' if daily else '2026-01-01T00:00:00Z', 'nav': '110'},
            'flows': []}


def event(amount='100', before='110', after='210'):
    return {'id': 'e1', 'at': '2025-07-02T12:00:00Z', 'amount': amount,
            'kind': 'external_deposit' if Decimal(amount) > 0 else 'external_withdrawal',
            'before': before, 'after': after}


class CashflowTest(unittest.TestCase):
    def blocked(self, data, reason):
        result = calculate(data)
        self.assertEqual(result['status'], 'BLOCKED', result)
        self.assertEqual(result['reason'], reason, result)
        self.assertIsNone(result['metrics'])

    def test_no_flow_and_input_unchanged(self):
        data = sample(); original = copy.deepcopy(data)
        result = calculate(data)
        self.assertEqual(Decimal(result['metrics']['twr']), Decimal('.1'))
        self.assertFalse(result['evidence_authenticated'])
        self.assertFalse(result['policy_approval_granted'])
        self.assertEqual(data, original)

    def test_deposit_twr(self):
        data = sample(); data['flows'] = [event()]; data['end']['nav'] = '231'
        self.assertEqual(Decimal(calculate(data)['metrics']['twr']), Decimal('.21'))

    def test_withdrawal_twr(self):
        data = sample(); data['flows'] = [event('-50', '110', '60')]; data['end']['nav'] = '66'
        self.assertEqual(Decimal(calculate(data)['metrics']['twr']), Decimal('.21'))

    def test_fee_reduces_nav(self):
        data = sample(); data['end']['nav'] = '99'
        self.assertEqual(Decimal(calculate(data)['metrics']['twr']), Decimal('-.01'))
        data['flows'] = [event('-1', '100', '99')]; data['flows'][0]['kind'] = 'fee'
        self.blocked(data, 'INVALID_FLOW_KIND_OR_SIGN')

    def test_flow_reconciliation(self):
        data = sample(); data['flows'] = [event(after='209.99')]
        self.blocked(data, 'FLOW_NAV_MISMATCH')

    def test_duplicate_is_idempotent_and_conflict_blocks(self):
        data = sample(); data['flows'] = [event(), event()]; data['end']['nav'] = '231'
        self.assertEqual(calculate(data)['unique_flow_count'], 1)
        data['flows'][1]['after'] = '211'
        self.blocked(data, 'DUPLICATE_CONFLICT')

    def test_timezone_same_instant_is_ambiguous(self):
        data = sample(); second = event(); second.update(id='e2', at='2025-07-02T21:00:00+09:00')
        data['flows'] = [event(), second]
        self.blocked(data, 'SIMULTANEOUS_FLOW_UNSUPPORTED')

    def test_timezone_and_date_precision(self):
        for value in ('2025-01-01', '2025-01-01T00:00:00'):
            data = sample(); data['start']['at'] = value
            self.blocked(data, 'TIMEZONE_REQUIRED')

    def test_malformed_amounts(self):
        for value in (True, 100, 1.0, None, 'NaN', 'Infinity', '1e2', '1'*129):
            with self.subTest(value=value):
                data = sample(); data['start']['nav'] = value
                self.blocked(data, 'INVALID_DECIMAL')

    def test_nonpositive_initial_and_negative_final(self):
        for key, value in (('start', '0'), ('start', '-1'), ('end', '-1')):
            data = sample(); data[key]['nav'] = value
            self.blocked(data, 'INVALID_NAV')

    def test_start_flow_and_future_flow_blocked(self):
        for at in ('2025-01-01T00:00:00Z', '2026-01-02T00:00:00Z'):
            data = sample(); data['flows'] = [event()]; data['flows'][0]['at'] = at
            self.blocked(data, 'FLOW_OUTSIDE_PERIOD')

    def test_terminal_withdrawal(self):
        data = sample(); row = event('-110', '110', '0'); row['at'] = data['end']['at']
        data['flows'] = [row]; data['end']['nav'] = '0'
        result = calculate(data)
        self.assertEqual(Decimal(result['metrics']['twr']), Decimal('.1'))
        self.assertTrue(result['metrics']['segment_closed'])
        data['end']['nav'] = '1'
        self.blocked(data, 'END_NAV_MISMATCH')

    def test_empty_segment_not_restarted(self):
        data = sample(); data['flows'] = [event('-110', '110', '0')]
        self.blocked(data, 'SEGMENT_ENDED')
        data['flows'] = [event('100', '0', '100')]
        self.blocked(data, 'SEGMENT_ENDED')

    def test_terminal_market_loss(self):
        data = sample(); data['end']['nav'] = '0'
        self.assertEqual(Decimal(calculate(data)['metrics']['twr']), -1)

    def test_dietz_half_period(self):
        data = sample('dietz'); row = event(); del row['before']; del row['after']
        data['flows'] = [row]; data['end']['nav'] = '210'
        result = calculate(data)
        self.assertAlmostEqual(float(result['metrics']['dietz']), 1/15)
        self.assertTrue(result['metrics']['approximation'])

    def test_dietz_nonpositive_denominator(self):
        data = sample('dietz'); row = event('-300'); del row['before']; del row['after']
        data['flows'] = [row]
        self.blocked(data, 'NONPOSITIVE_DIETZ_DENOMINATOR')

    def test_mwr_one_year(self):
        result = calculate(sample('mwr'))
        self.assertAlmostEqual(result['metrics']['annualized_mwr'], .1, places=10)
        self.assertLessEqual(abs(result['metrics']['solver']['relative_npv_residual']), 1e-12)

    def test_mwr_short_period_and_date_rejection(self):
        data = sample('mwr'); data['end']['at'] = '2025-07-02'
        result = calculate(data)
        self.assertEqual(result['metrics']['primary_display'], 'period_mwr')
        self.assertAlmostEqual(result['metrics']['period_mwr'], .1, places=10)
        data['end']['at'] = '2025-07-02T00:00:00Z'
        self.blocked(data, 'INVALID_DATE')

    def test_mwr_mid_period_deposit_known_root(self):
        data = sample('mwr'); data['end'] = {'at': '2027-01-01', 'nav': '231'}
        data['flows'] = [{'id': 'e1', 'at': '2026-01-01', 'amount': '100', 'kind': 'external_deposit'}]
        self.assertAlmostEqual(calculate(data)['metrics']['annualized_mwr'], .1, places=10)

    def test_mwr_multiple_sign_changes(self):
        data = sample('mwr'); data['end'] = {'at': '2027-01-01', 'nav': '0'}
        data['flows'] = [dict(id='a', at='2026-01-01', amount='-230', kind='external_withdrawal'),
                         dict(id='b', at='2027-01-01', amount='132', kind='external_deposit')]
        self.blocked(data, 'AMBIGUOUS_CASHFLOW_PATTERN')

    def test_mwr_same_day_and_final_flow(self):
        data = sample('mwr'); data['end']['nav'] = '0'
        data['flows'] = [dict(id='a', at='2026-01-01', amount='-110', kind='external_withdrawal')]
        self.assertAlmostEqual(calculate(data)['metrics']['annualized_mwr'], .1, places=10)
        data['flows'].append(dict(id='b', at='2026-01-01', amount='10', kind='external_deposit'))
        self.assertAlmostEqual(calculate(data)['metrics']['annualized_mwr'], 0, places=10)

    def test_mwr_no_sign_change_and_bracket_failure(self):
        data = sample('mwr'); data['end']['nav'] = '0'
        self.blocked(data, 'NO_SIGN_CHANGE')
        data['end']['nav'] = '1' + '0'*30
        self.blocked(data, 'ROOT_NOT_BRACKETED')

    def test_schema_containers_and_missing_fields(self):
        self.blocked([], 'INVALID_INPUT')
        for key, value, reason in [('flows', {}, 'INVALID_FLOWS'), ('start', None, 'INVALID_BOUNDARY'),
                                   ('scope_id', '', 'MISSING_SCOPE'), ('source_ref', '', 'MISSING_SOURCE_REF'),
                                   ('method', [], 'INVALID_METHOD')]:
            data = sample(); data[key] = value; self.blocked(data, reason)

    def test_unsupported_raw_ledger_fields(self):
        for key, value in [('currency', 'USD'), ('status', 'planned'), ('transfer_id', 't1')]:
            data = sample(); row = event(); row[key] = value; data['flows'] = [row]
            self.blocked(data, 'UNSUPPORTED_FIELD')

    def test_flow_sort_order(self):
        data = sample(); first = event(); second = event('10', '210', '220')
        second.update(id='e2', at='2025-08-01T00:00:00Z')
        data['flows'] = [second, first]; data['end']['nav'] = '242'
        self.assertEqual(Decimal(calculate(data)['metrics']['twr']), Decimal('.21'))

    def test_cli_success_and_blocked(self):
        script = Path(__file__).resolve().parents[1] / 'portfolio_cashflow.py'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'input.json'
            for payload, code in [(sample(), 0), ({}, 2)]:
                path.write_text(json.dumps(payload))
                result = subprocess.run([sys.executable, str(script), '--input', str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIn('status', json.loads(result.stdout))
            path.write_text('{')
            result = subprocess.run([sys.executable, str(script), '--input', str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['reason'], 'INPUT_READ_ERROR')


if __name__ == '__main__':
    unittest.main()
