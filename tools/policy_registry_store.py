"""Single-writer, atomic research ledger; projections are recoverable caches.

POSIX local filesystem only. Hashes detect accidental edits, not a malicious
writer able to replace the ledger and recompute hashes. No human authentication.
"""
import copy
import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


@contextmanager
def locked(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.registry.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield root
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def atomic_write(path, content):
    fd, name = tempfile.mkstemp(prefix='.registry-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_ledger(root):
    path = root / 'registry.json'
    if not path.exists():
        if (root / 'active.json').exists() or (root / 'events.jsonl').exists() or list(root.glob('policy-*.json')):
            raise ValueError('legacy registry requires separate reviewed migration; files preserved')
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('records'), list):
        raise ValueError('invalid registry schema')
    records = data['records']
    previous = None
    versions, events = set(), set()
    policy_id = None
    for record in records:
        payload = record.get('payload', {})
        if record.get('hash') != digest(payload) or payload.get('previous_hash') != previous:
            raise ValueError('ledger integrity failure')
        policy, event, draft = payload['policy'], payload['event'], payload['draft']
        version = policy['version']
        if not isinstance(version, str) or not version or not all(c.isalnum() or c in '._-' for c in version):
            raise ValueError('unsafe stored version')
        if version in versions or event['event_id'] in events:
            raise ValueError('duplicate ledger entry')
        if policy_id is not None and policy['policy_id'] != policy_id:
            raise ValueError('mixed policy registry')
        if (policy.get('status') != 'research_active' or policy.get('approval_authenticated') is not False
                or policy.get('operational_use_allowed') is not False or event['document_hash'] != digest(draft)):
            raise ValueError('invalid research record')
        policy_id = policy['policy_id']
        versions.add(version)
        events.add(event['event_id'])
        previous = record['hash']
    return records


def projections(records):
    result = {}
    if records:
        for record in records:
            policy = record['payload']['policy']
            result['policy-' + policy['version'] + '.json'] = encode(policy)
        result['active.json'] = encode(records[-1]['payload']['policy'])
        result['events.jsonl'] = ''.join(encode(r['payload']['event']) + '\n' for r in records)
    return result


def mismatches(root, records):
    expected = projections(records)
    errors = [name for name, content in expected.items()
              if not (root / name).exists() or (root / name).read_text(encoding='utf-8') != content]
    errors += [p.name for p in root.glob('policy-*.json') if p.name not in expected]
    return sorted(errors)


def project(root, records):
    for name, content in projections(records).items():
        atomic_write(root / name, content)


def persist(draft, event, policy, directory):
    event_id = event.get('event_id')
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError('event_id required')
    with locked(directory) as root:
        records = read_ledger(root)
        if records and records[0]['payload']['policy']['policy_id'] != policy['policy_id']:
            raise ValueError('one policy_id per registry')
        for record in records:
            prior = record['payload']
            if prior['event']['event_id'] == event_id:
                if prior['draft'] != draft or prior['event'] != event:
                    raise ValueError('event_id conflict')
                project(root, records)
                return copy.deepcopy(prior['policy'])
            if prior['policy']['version'] == policy['version']:
                raise FileExistsError('immutable version conflict')
        payload = {'draft': draft, 'event': event, 'policy': policy,
                   'previous_hash': records[-1]['hash'] if records else None}
        records.append({'payload': payload, 'hash': digest(payload)})
        # The single authoritative commit point; projection errors are retryable.
        atomic_write(root / 'registry.json', encode({'schema': 1, 'records': records}))
        project(root, records)
        return copy.deepcopy(policy)


def inspect_registry(directory, *, repair=False):
    with locked(directory) as root:
        records = read_ledger(root)
        errors = mismatches(root, records)
        if repair:
            project(root, records)
        return {'mode': 'research_only', 'approval_authenticated': False,
                'operational_use_allowed': False, 'record_count': len(records),
                'head_hash': records[-1]['hash'] if records else None,
                'current': records[-1]['payload']['policy'] if records else None,
                'projection_errors': mismatches(root, records) if repair else errors,
                'repaired_from': errors if repair else []}
