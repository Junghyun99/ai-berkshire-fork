"""Synthetic fixtures only; no authenticated approvals or real policy writes."""
import copy
import json
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_policy import example
from policy_registry import register, digest
from policy_registry_store import inspect_registry, atomic_write
from policy_validator import check_policy


def inputs(version='1.0', event_id='fixture-1'):
    draft = example()
    draft.update(status='draft', approved_by=None, approved_at=None, version=version)
    draft['provenance']['policy_version'] = version
    draft['feasibility_review']['policy_version'] = version
    event = dict(event_id=event_id, event_type='POLICY_APPROVED', actor_type='user',
                 actor_id='user1', policy_id='example', version=version,
                 approved_at='2026-10-28T10:00:00+09:00', document_hash=digest(draft))
    return draft, event


def contender(directory, event_id, queue):
    try:
        register(*inputs(event_id=event_id), directory, research_only=True)
        queue.put('ok')
    except FileExistsError:
        queue.put('conflict')


class RegistryIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def add(self, version='1.0', event_id='fixture-1'):
        return register(*inputs(version, event_id), self.root, research_only=True)

    def test_default_blocks_self_asserted_approval(self):
        with self.assertRaisesRegex(ValueError, 'authenticated approval unavailable'):
            register(*inputs(), self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_research_policy_not_eligible_for_operational_validator(self):
        policy = self.add()
        self.assertTrue(check_policy(policy))
        self.assertFalse(policy['approval_authenticated'])
        self.assertFalse(policy['operational_use_allowed'])

    def test_idempotent_retry(self):
        self.assertEqual(self.add(), self.add())
        self.assertEqual(inspect_registry(self.root)['record_count'], 1)

    def test_event_reuse_changed_content_blocked(self):
        self.add()
        with self.assertRaisesRegex(ValueError, 'event_id conflict'):
            self.add('2.0')
        self.assertEqual(inspect_registry(self.root)['record_count'], 1)

    def test_missing_event_id(self):
        draft, event = inputs()
        del event['event_id']
        with self.assertRaisesRegex(ValueError, 'event_id required'):
            register(draft, event, self.root, research_only=True)

    def test_new_version_preserves_old_archive(self):
        old = self.add()
        self.add('2.0', 'fixture-2')
        self.assertEqual(json.loads((self.root/'policy-1.0.json').read_text()), old)
        self.assertEqual(inspect_registry(self.root)['current']['version'], '2.0')

    def test_failure_before_commit_preserves_previous_state(self):
        self.add()
        with patch('policy_registry_store.os.replace', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                self.add('2.0', 'fixture-2')
        result = inspect_registry(self.root)
        self.assertEqual(result['record_count'], 1)
        self.assertEqual(result['projection_errors'], [])

    def test_each_projection_failure_recovered_by_retry(self):
        for name in ('policy-1.0.json', 'events.jsonl', 'active.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                def fail(path, content):
                    if path.name == name:
                        raise OSError('injected projection failure')
                    atomic_write(path, content)
                with patch('policy_registry_store.atomic_write', side_effect=fail):
                    with self.assertRaises(OSError):
                        register(*inputs(), directory, research_only=True)
                self.assertEqual(inspect_registry(directory)['record_count'], 1)
                register(*inputs(), directory, research_only=True)
                result = inspect_registry(directory)
                self.assertEqual(result['record_count'], 1)
                self.assertEqual(result['projection_errors'], [])

    def test_projection_edit_detected_and_explicitly_repaired(self):
        self.add()
        (self.root/'active.json').write_text('{}')
        self.assertEqual(inspect_registry(self.root)['projection_errors'], ['active.json'])
        result = inspect_registry(self.root, repair=True)
        self.assertEqual(result['repaired_from'], ['active.json'])
        self.assertEqual(result['projection_errors'], [])

    def test_ledger_edit_blocks_recovery(self):
        self.add()
        path = self.root/'registry.json'
        data = json.loads(path.read_text())
        data['records'][0]['payload']['policy']['owner'] = 'other'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'integrity failure'):
            inspect_registry(self.root, repair=True)

    def test_legacy_registry_preserved_and_blocked(self):
        path = self.root/'active.json'
        path.write_text('{"legacy":true}')
        with self.assertRaisesRegex(ValueError, 'legacy registry'):
            self.add()
        self.assertEqual(path.read_text(), '{"legacy":true}')

    def test_different_policy_id_blocked(self):
        self.add()
        draft, event = inputs('2.0', 'fixture-2')
        draft['policy_id'] = event['policy_id'] = 'other'
        draft['provenance']['policy_id'] = 'other'
        draft['feasibility_review']['policy_id'] = 'other'
        event['document_hash'] = digest(draft)
        with self.assertRaisesRegex(ValueError, 'one policy_id'):
            register(draft, event, self.root, research_only=True)

    def test_concurrent_conflicting_version(self):
        context = multiprocessing.get_context('fork')
        queue = context.Queue()
        processes = [context.Process(target=contender, args=(str(self.root), f'e-{i}', queue)) for i in range(4)]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(10)
                self.assertEqual(process.exitcode, 0)
            outcomes = [queue.get(timeout=3) for _ in processes]
            self.assertEqual(outcomes.count('ok'), 1)
            self.assertEqual(outcomes.count('conflict'), 3)
            self.assertEqual(inspect_registry(self.root)['projection_errors'], [])
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join()
            queue.close()
            queue.join_thread()

    def test_no_mutation_of_inputs(self):
        draft, event = inputs()
        saved = copy.deepcopy((draft, event))
        register(draft, event, self.root, research_only=True)
        self.assertEqual((draft, event), saved)
