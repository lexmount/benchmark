"""Per-response accounting only; no model requests and no changes to transport.

Rates come from a sanitized deployment /model/info snapshot, never constants.
Semantics adapted from LiteLLM 01de1a686dd528e61364f8898e65cfd5dbf0821d:
  litellm/litellm_core_utils/llm_cost_calc/utils.py:_get_token_base_cost,
  generic_cost_per_token, parse_prompt_tokens_details; OpenAI/DeepSeek delegate
  to that generic calculator. Above-N thresholds use total prompt tokens > N,
  price the entire request, and include cache reads in the threshold count.
  Reasoning is a subset of output, not an additional output charge.
References: https://docs.litellm.ai/docs/proxy/response_headers
            https://docs.litellm.ai/docs/proxy/model_cost_map
This small stdlib adapter preserves unknowns instead of importing a whole proxy.
It estimates standard token pricing; authoritative per-call headers take priority.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

PRIVATE_CONFIG_PATH = Path(__file__).resolve().parent.parent / '.private' / 'model.json'
MODELS = ('deepseek-v4.1-flash', 'gpt-6.1-sol')
SOURCE_COMMIT = '01de1a686dd528e61364f8898e65cfd5dbf0821d'
COST_HEADERS = {
    'x-litellm-response-cost': 'total',
    'x-litellm-response-cost-input': 'uncached_input',
    'x-litellm-response-cost-output': 'output',
    'x-litellm-response-cost-cache-read': 'cache_read',
    'x-litellm-response-cost-cache-creation': 'cache_creation',
    'x-litellm-response-cost-reasoning': 'reasoning_subset_of_output',
    'x-litellm-response-cost-tool-usage': 'tool_usage',
}
META_HEADERS = ('x-litellm-version', 'x-litellm-call-id', 'x-request-id',
                'request-id', 'x-litellm-model-id', 'x-litellm-model-group')
RATE_PREFIXES = ('input_cost_per_token', 'output_cost_per_token',
                 'cache_read_input_token_cost', 'cache_creation_input_token_cost')
THRESHOLD = re.compile(r'^(' + '|'.join(RATE_PREFIXES) + r')_above_(\d+k?)_tokens$')
PRICE_FIELD = re.compile(r'^(?:input_cost_per_|output_cost_per_|cache_read_input_token_cost|cache_creation_input_token_cost)')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _integer(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _mapping(value):
    if isinstance(value, Mapping):
        return value
    dump = getattr(value, 'model_dump', None)
    if callable(dump):
        candidate = dump()
        return candidate if isinstance(candidate, Mapping) else None
    return None


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as f:
        temporary = Path(f.name)
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    temporary.replace(path)
    return data


def record_billing(destination, number, response):
    """Write only NNNN.billing.json; do not read body, send requests or mutate response.

    Only this request's cost/metadata whitelist is retained. Authorization,
    x-litellm-key-spend, budgets, API bases and other cumulative/key data are not.
    A reported finite zero is valid. Missing/invalid/nonfinite values stay null.
    """
    if not isinstance(number, int) or isinstance(number, bool) or number < 0:
        raise ValueError('number must be a nonnegative integer')
    headers = {str(k).lower(): v for k, v in response.headers.items()}
    retained, invalid = {}, []
    components = {}
    for header, component in COST_HEADERS.items():
        value = _number(headers.get(header))
        if header in headers:
            retained[header] = value
            if value is None:
                invalid.append(header)
        if component != 'total':
            components[component] = value
    for header in META_HEADERS:
        if header in headers:
            # These are request/deployment identifiers, never all-key spend.
            retained[header] = ''.join(c for c in str(headers[header]) if c.isprintable())[:512]
    total = retained.get('x-litellm-response-cost')
    summable = [components[k] for k in ('uncached_input', 'cache_read', 'cache_creation', 'output', 'tool_usage')]
    complete = all(v is not None for v in summable)
    data = {
        'schema_version': 1, 'recorded_at_utc': _now(), 'request_number': number,
        'http_status': getattr(response, 'status_code', None),
        'cost_status': 'reported' if total is not None else 'unknown',
        'cost_usd': total, 'estimate': False if total is not None else None,
        'whitelisted_headers': retained, 'invalid_cost_headers': invalid,
        'components_usd': components,
        'component_sum_usd': float(sum(Decimal(str(v)) for v in summable)) if complete else None,
        'component_sum_complete': complete,
        'reasoning_is_subset_of_output': True,
        'request_id': retained.get('x-litellm-call-id') or retained.get('x-request-id') or retained.get('request-id'),
        'litellm_version': retained.get('x-litellm-version'),
        'source': 'per_response_proxy_headers',
    }
    return _write(Path(destination) / f'{number:04d}.billing.json', data)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward private proxy authorization to a redirect.


def _sanitize_pricing(payload):
    rows = payload.get('data') if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return {}, ['model_info_response_has_no_data_list']
    models, errors = {}, []
    for model in MODELS:
        variants, invalid = [], set()
        count = 0
        for row in rows:
            if not isinstance(row, Mapping) or row.get('model_name') != model:
                continue
            count += 1
            info = row.get('model_info')
            if not isinstance(info, Mapping):
                invalid.add('model_info_missing')
                continue
            prices = {}
            for key, value in info.items():
                if isinstance(key, str) and PRICE_FIELD.match(key):
                    parsed = _number(value)
                    prices[key] = parsed
                    if value is not None and parsed is None:
                        invalid.add(key)
            if prices not in variants:
                variants.append(prices)
        if count == 0:
            errors.append(f'model_missing:{model}')
            continue
        if len(variants) != 1:
            errors.append(f'pricing_deployments_ambiguous:{model}')
        models[model] = {
            'model_info': variants[0] if len(variants) == 1 else None,
            'deployment_count': count, 'distinct_pricing_count': len(variants),
            'invalid_pricing_fields': sorted(invalid),
        }
    return models, errors


def capture_pricing_snapshot(path):
    """Explicitly GET configured base/model/info once, saving only safe cost fields.

    Authorized private config is read in memory only. The raw response and
    litellm_params/API keys are never persisted; its SHA256 is retained instead.
    Returns a snapshot even on failure, with unknown status and no leaked body.
    """
    data = {'schema_version': 1, 'captured_at_utc': _now(), 'status': 'unknown',
            'source': 'authorized_proxy_GET_model_info', 'source_response_sha256': None,
            'http_status': None, 'litellm_version': None, 'models': {}, 'errors': [],
            'calculator_reference_commit': SOURCE_COMMIT}
    try:
        config = json.loads(PRIVATE_CONFIG_PATH.read_text())
        base, key = config.get('base_url'), config.get('api_key')
        if not isinstance(base, str) or not isinstance(key, str) or not key:
            raise ValueError('invalid_private_config')
        parsed = urlsplit(base)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('invalid_proxy_base_url')
        req = Request(base.rstrip('/') + '/model/info', method='GET',
                      headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
        with build_opener(_NoRedirect()).open(req, timeout=20) as response:
            data['http_status'] = response.status
            data['litellm_version'] = response.headers.get('x-litellm-version')
            raw = response.read(8 * 1024 * 1024 + 1)
        data['source_response_sha256'] = hashlib.sha256(raw).hexdigest()
        if len(raw) > 8 * 1024 * 1024:
            data['errors'].append('model_info_response_exceeds_8MiB')
        else:
            data['models'], data['errors'] = _sanitize_pricing(json.loads(raw))
            if not data['errors']:
                data['status'] = 'captured'
    except HTTPError as exc:
        data['http_status'] = exc.code
        data['errors'].append('http_error')
        exc.close()
    except Exception as exc:
        # No exception body/URL/config: it can contain provider keys or data.
        data['errors'].append(type(exc).__name__)
    return _write(path, data)


def _unknown(model, reason, **extra):
    return {'schema_version': 1, 'model': model, 'status': 'unknown', 'estimate': True,
            'cost_usd': None, 'reason': reason, **extra}


def _count(values):
    present = [v for v in values if v is not None]
    if not present:
        return None, False
    parsed = [_integer(v) for v in present]
    if any(v is None for v in parsed) or len(set(parsed)) != 1:
        return None, True
    return parsed[0], False


def reconstruct_cost(usage, model, pricing_snapshot):
    """Estimate token cost using captured deployment rates; unknown is never zero.

    Supports OpenAI-compatible total prompt/input tokens (cache included),
    completion/output tokens (reasoning included), cached_tokens or DeepSeek
    hit/miss counters, and optional cache-write tokens. Does not calculate
    priority/flex/batch/tool/region/TTL charges; header billing is authoritative.
    """
    usage = _mapping(usage)
    if usage is None:
        return _unknown(model, 'usage_missing_or_invalid')
    if isinstance(pricing_snapshot, (str, Path)):
        try:
            pricing_snapshot = json.loads(Path(pricing_snapshot).read_text())
        except Exception:
            return _unknown(model, 'pricing_snapshot_unreadable')
    snapshot = _mapping(pricing_snapshot)
    models = (snapshot or {}).get('models')
    entry = models.get(model) if isinstance(models, Mapping) else None
    if not isinstance(entry, Mapping) or not isinstance(entry.get('model_info'), Mapping):
        return _unknown(model, 'model_pricing_missing_or_ambiguous')
    prices = entry['model_info']
    if entry.get('invalid_pricing_fields'):
        return _unknown(model, 'pricing_snapshot_contains_invalid_rates')
    if usage.get('service_tier') not in (None, 'default', 'standard'):
        return _unknown(model, 'unsupported_service_tier')
    pd = _mapping(usage.get('prompt_tokens_details')) or {}
    ind = _mapping(usage.get('input_tokens_details')) or {}
    od = _mapping(usage.get('completion_tokens_details')) or _mapping(usage.get('output_tokens_details')) or {}
    prompt, bad_prompt = _count([usage.get('prompt_tokens'), usage.get('input_tokens')])
    output, bad_output = _count([usage.get('completion_tokens'), usage.get('output_tokens')])
    cached, bad_cached = _count([pd.get('cached_tokens'), ind.get('cached_tokens'), usage.get('prompt_cache_hit_tokens')])
    creation, bad_creation = _count([pd.get('cache_write_tokens'), pd.get('cache_creation_tokens'), ind.get('cache_write_tokens'), ind.get('cache_creation_tokens'), usage.get('cache_creation_input_tokens')])
    miss, bad_miss = _count([usage.get('prompt_cache_miss_tokens')])
    reasoning, bad_reasoning = _count([od.get('reasoning_tokens')])
    if any((bad_prompt, bad_output, bad_cached, bad_creation, bad_miss, bad_reasoning)):
        return _unknown(model, 'invalid_or_conflicting_token_counts')
    if prompt is None or output is None:
        return _unknown(model, 'prompt_or_output_tokens_missing')
    creation = 0 if creation is None else creation
    if cached is None:
        if miss is not None:
            cached = prompt - miss - creation
        elif prompt == 0:
            cached = 0
        else:
            return _unknown(model, 'cache_read_tokens_missing')
    if cached < 0 or cached + creation > prompt or (miss is not None and miss != prompt - cached - creation):
        return _unknown(model, 'cache_tokens_exceed_or_conflict_with_prompt')
    if reasoning is not None and reasoning > output:
        return _unknown(model, 'reasoning_tokens_exceed_output')
    if creation and (pd.get('cache_creation_token_details') or ind.get('cache_creation_token_details')):
        return _unknown(model, 'cache_creation_TTL_pricing_not_supported')
    rates = {prefix: _number(prices.get(prefix)) for prefix in RATE_PREFIXES}
    thresholds = {}
    for key, value in prices.items():
        match = THRESHOLD.fullmatch(key)
        if match and value is not None:
            unit = match.group(2)
            threshold = int(unit[:-1]) * 1000 if unit.endswith('k') else int(unit)
            if _number(value) is None:
                return _unknown(model, 'invalid_threshold_rate')
            thresholds.setdefault(threshold, {})[match.group(1)] = _number(value)
    applied = []
    for threshold in sorted(thresholds):
        if prompt > threshold:
            rates.update(thresholds[threshold])
            applied.append(threshold)
    if rates['input_cost_per_token'] is None or rates['output_cost_per_token'] is None:
        return _unknown(model, 'input_or_output_rate_missing')
    fallbacks = []
    for prefix in RATE_PREFIXES[2:]:
        if rates[prefix] is None:
            rates[prefix] = rates['input_cost_per_token']
            fallbacks.append(prefix)
    counts = {'prompt_total': prompt, 'uncached_input': prompt - cached - creation,
              'cache_read': cached, 'cache_creation': creation, 'output_including_reasoning': output,
              'reasoning_subset_of_output': reasoning}
    components = {
        'uncached_input': Decimal(counts['uncached_input']) * Decimal(str(rates[RATE_PREFIXES[0]])),
        'output': Decimal(output) * Decimal(str(rates[RATE_PREFIXES[1]])),
        'cache_read': Decimal(cached) * Decimal(str(rates[RATE_PREFIXES[2]])),
        'cache_creation': Decimal(creation) * Decimal(str(rates[RATE_PREFIXES[3]])),
    }
    cost = float(sum(components.values()))
    if not math.isfinite(cost):
        return _unknown(model, 'cost_overflow')
    return {'schema_version': 1, 'model': model, 'status': 'estimated', 'estimate': True,
            'cost_usd': cost, 'components_usd': {k: float(v) for k, v in components.items()},
            'token_counts': counts, 'rates_usd_per_token': rates,
            'applied_threshold_tokens': applied[-1] if applied else None,
            'threshold_semantics': 'total_prompt_strictly_greater; whole_request_rate',
            'cache_rate_fallback_to_input': fallbacks,
            'reasoning_is_subset_of_output': True,
            'pricing_captured_at_utc': snapshot.get('captured_at_utc'),
            'pricing_source_response_sha256': snapshot.get('source_response_sha256'),
            'scope': 'standard token-priced request; excludes unreported tools, discounts and margins',
            'calculator_reference_commit': SOURCE_COMMIT}
