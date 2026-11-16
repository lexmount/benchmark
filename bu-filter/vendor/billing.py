"""Per-response cost headers reused from the existing 5090 evaluator; no requests."""
import json, math, tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

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
