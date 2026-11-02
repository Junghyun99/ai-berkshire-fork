"""Mechanical IPS completeness checks; does not authenticate evidence or approve policy."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation


def text(value):
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() not in {'TBD', 'UNKNOWN', 'TODO'}


def names(value, empty=False):
    return isinstance(value, list) and (empty or bool(value)) and all(text(x) for x in value) and len(set(value)) == len(value)


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError('invalid number')
    try:
        n = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('invalid number') from exc
    if not n.is_finite():
        raise ValueError('nonfinite number')
    return n


def day(value):
    if not text(value):
        raise ValueError('missing date')
    if len(value) == 10:
        return date.fromisoformat(value)
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timestamp needs timezone')
    return dt.astimezone(timezone.utc).date()


def supplemental_checks(p, as_of=None):
    errors = []
    def fail(gate, message): errors.append(gate + ': ' + message)
    def required(gate, obj, keys):
        for key in keys:
            if not text(obj.get(key)):
                fail(gate, 'UNKNOWN missing/invalid ' + key)
    def obj(gate, value, label):
        if not isinstance(value, dict):
            fail(gate, 'UNKNOWN structured ' + label + ' required')
            return {}
        return value
    today = day(as_of) if as_of is not None else datetime.now(timezone.utc).date()
    required('G01', p, ('owner', 'policy_id', 'approved_by'))
    if not names(p.get('portfolio_ids')): fail('G01', 'UNKNOWN portfolio_ids required')
    if text(p.get('owner')) and p.get('approved_by') != p['owner']:
        fail('G01', 'approver must match owner in single-owner model')
    scope = obj('G02', p.get('policy_scope'), 'policy_scope')
    if not names(scope.get('accounts')): fail('G02', 'UNKNOWN account categories required')
    currency = p.get('base_currency')
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isalpha() or not currency.isupper():
        fail('G02', 'invalid three-letter base_currency')
    required('G03', p, ('objective', 'investment_horizon'))
    flows = p.get('cash_flow_needs')
    # Empty list explicitly means no scheduled external flow; missing is unknown.
    if not isinstance(flows, list):
        fail('G03', 'UNKNOWN cash_flow_needs must be explicit event list')
    else:
        for flow in flows:
            f = obj('G03', flow, 'cashflow event')
            try:
                if f.get('type') not in ('contribution', 'withdrawal') or number(f.get('amount')) <= 0 or f.get('currency') != currency:
                    raise ValueError()
                day(f.get('date'))
            except (ValueError, TypeError): fail('G03', 'invalid cashflow event')
    required('G04', p, ('risk_capacity', 'risk_willingness'))
    limits = obj('G04', p.get('risk_limits'), 'risk_limits')
    required('G04', limits, ('measurement_method',))
    for key in ('single_name_max_pct', 'sector_max_pct', 'liquidity_min_pct'):
        try:
            if not 0 <= number(limits.get(key)) <= 100: raise ValueError()
        except ValueError: fail('G04', 'UNKNOWN/invalid ' + key)
    try:
        if number(limits.get('gross_leverage_max')) < 1: raise ValueError()
    except ValueError: fail('G04', 'UNKNOWN/invalid gross_leverage_max')
    rules = obj('G05', p.get('asset_rules'), 'asset_rules')
    for key in ('leverage_allowed', 'derivatives_allowed'):
        if type(rules.get(key)) is not bool: fail('G05', 'UNKNOWN explicit boolean ' + key + ' required')
    if rules.get('leverage_allowed') is False:
        try:
            if number(limits.get('gross_leverage_max')) > 1: fail('G05', 'leverage prohibited but cap exceeds 1')
        except ValueError: pass  # G04 already reports invalid/missing cap.
    allowed, banned = p.get('eligible_assets'), p.get('prohibited_assets')
    if not names(allowed) or not names(banned, empty=True): fail('G05', 'invalid/duplicate asset lists')
    targets = p.get('strategic_targets')
    if isinstance(targets, dict) and names(allowed):
        if any(not text(k) or k not in allowed for k in targets): fail('G06', 'allocation contains ineligible asset')
    if limits.get('currency') != currency: fail('G07', 'risk limit currency mismatch/missing')
    try:
        if day(limits.get('as_of')) > today: raise ValueError()
    except (ValueError, TypeError): fail('G07', 'UNKNOWN/invalid risk limit as_of')
    bench = obj('G08', p.get('benchmark'), 'benchmark')
    if bench.get('exception') is True:
        required('G08', bench, ('reason', 'approved_by', 'evidence_ref'))
        if bench.get('approved_by') != p.get('owner'): fail('G08', 'benchmark exception owner mismatch')
    else:
        required('G08', bench, ('name', 'evaluation_period', 'return_basis'))
        if bench.get('currency') != currency: fail('G08', 'benchmark currency mismatch/missing')
    approval = obj('G09', p.get('approval_rules'), 'approval_rules')
    required('G09', approval, ('review_frequency', 'amendment_rule'))
    rebalance = obj('G09', p.get('rebalance_policy'), 'rebalance_policy')
    required('G09', rebalance, ('frequency',))
    try:
        approved, effective = day(p.get('approved_at')), day(p.get('effective_at'))
        if approved > effective or approved > today or effective > today:
            fail('G09', 'approval/effective date order or future date')
        if p.get('expiry_rule') == 'until_superseded':
            if p.get('expires_at') is not None: fail('G09', 'conflicting expiry fields')
        elif p.get('expiry_rule') == 'fixed_date':
            expiry = day(p.get('expires_at'))
            if expiry <= effective or today >= expiry: fail('G09', 'expired/invalid validity period')
        else: fail('G09', 'UNKNOWN expiry_rule required')
    except (ValueError, TypeError): fail('G09', 'UNKNOWN/invalid approval or validity dates')
    required('G10', p, ('version',))
    provenance = obj('G10', p.get('provenance'), 'provenance')
    if not names(provenance.get('sources')): fail('G10', 'UNKNOWN source references required')
    required('G10', provenance, ('approval_ref', 'revision_ref'))
    if (provenance.get('policy_id'), provenance.get('policy_version')) != (p.get('policy_id'), p.get('version')):
        fail('G10', 'provenance policy/version mismatch')
    sources = obj('G11', p.get('validation_sources'), 'validation_sources')
    for kind in ('prices', 'fx', 'holdings'):
        source = obj('G11', sources.get(kind), kind)
        required('G11', source, ('evidence_ref',))
        if source.get('status') != 'available': fail('G11', 'UNKNOWN/unavailable ' + kind)
        try:
            if day(source.get('as_of')) > today: raise ValueError()
        except (ValueError, TypeError): fail('G11', 'UNKNOWN/invalid source as_of: ' + kind)
    review = obj('G12', p.get('feasibility_review'), 'feasibility_review')
    required('G12', review, ('reviewer', 'reason', 'evidence_ref'))
    if review.get('actor_type') != 'user' or review.get('result') != 'pass':
        fail('G12', 'UNKNOWN explicit human review record required')
    if review.get('unresolved_conflicts') != []: fail('G12', 'UNKNOWN/unresolved feasibility conflicts')
    if (review.get('policy_id'), review.get('policy_version')) != (p.get('policy_id'), p.get('version')):
        fail('G12', 'review policy/version mismatch')
    try:
        reviewed = day(review.get('reviewed_at'))
        if reviewed > day(p.get('approved_at')) or reviewed > today: fail('G12', 'review occurs after approval/as_of')
    except (ValueError, TypeError): fail('G12', 'UNKNOWN/invalid review date')
    return errors
