"""
Unit tests (no server, no browser) that every Render deployment's static
frontend sends its API calls to ITS OWN backend.

Regression guard for a real bug: frontend/config.js only knew about
localhost and the demo host, so the tester frontend
(abstractly-tester.onrender.com) fell through to the PRODUCTION API.
That's wrong twice over -- a tester's uploads would aim at prod's
database, and the tester site's own CSP (connect-src) only allows
abstractly-tester-api, so the browser blocked every call anyway.

Both sides of each pairing are derived from render.yaml rather than
hardcoded here, so adding a fourth deployment pair later without
updating config.js fails this test instead of silently routing to prod:
  - each Docker API service's ADMIN_ALLOWED_ORIGINS names its frontend's
    real (possibly Render-suffixed) origin
  - each static service's CSP connect-src names the API it may call
config.js is parsed, not executed, so this needs no Node install.
"""

import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RENDER_YAML = os.path.join(ROOT, 'render.yaml')
CONFIG_JS = os.path.join(ROOT, 'frontend', 'config.js')


def _render_services():
    """Split render.yaml into one text block per service, keyed by name.
    Regex rather than PyYAML because PyYAML isn't a project dependency."""
    with open(RENDER_YAML) as f:
        text = f.read()
    blocks = re.split(r'\n  - type: ', text)[1:]
    services = {}
    for block in blocks:
        name = re.search(r'^\s*name: (\S+)', block, re.M).group(1)
        services[name] = block
    return services


def _api_frontend_pairs():
    """(frontend_host, api_host) for every Docker API service."""
    pairs = []
    for name, block in _render_services().items():
        if 'runtime: docker' not in block:
            continue
        origin = re.search(
            r'key: ADMIN_ALLOWED_ORIGINS\s+value: https://(\S+)', block
        ).group(1)
        pairs.append((origin, f'{name}.onrender.com'))
    return pairs


def _csp_connect_hosts():
    """{static service name: set of https hosts its CSP connect-src allows}"""
    result = {}
    for name, block in _render_services().items():
        if 'runtime: static' not in block:
            continue
        connect = re.search(r'connect-src ([^;]+);', block).group(1)
        result[name] = set(re.findall(r'https://(\S+)', connect))
    return result


def _resolve_api_base(hostname):
    """Mirror config.js's API_BASE_URL logic for a deployed hostname:
    the first `host === '<x>'` branch that matches wins, else the final
    fallback return."""
    with open(CONFIG_JS) as f:
        js = f.read()
    for host, url in re.findall(
        r"host === '([^']+)'\)\s*\{\s*(?://[^\n]*\s*)*return '([^']+)'", js
    ):
        if host == hostname:
            return url
    return re.findall(r"return '(https://[^']+)';", js)[-1]


def test_render_yaml_has_prod_tester_and_demo_pairs():
    hosts = {api for _, api in _api_frontend_pairs()}
    assert hosts == {
        'abstractly-api.onrender.com',
        'abstractly-tester-api.onrender.com',
        'abstractly-demo-api.onrender.com',
    }, hosts


def test_every_frontend_routes_to_its_own_api():
    for frontend_host, api_host in _api_frontend_pairs():
        got = _resolve_api_base(frontend_host)
        assert got == f'https://{api_host}', (
            f'{frontend_host} sends API calls to {got}, expected https://{api_host}'
        )


def test_tester_frontend_never_routes_to_production():
    # The specific bug, stated directly.
    assert _resolve_api_base('abstractly-tester.onrender.com') == \
        'https://abstractly-tester-api.onrender.com'


def test_each_frontend_csp_allows_the_api_config_js_picks():
    csp = _csp_connect_hosts()
    for frontend_host, api_host in _api_frontend_pairs():
        # The one static service whose CSP was written for this API.
        matching = [name for name, hosts in csp.items() if api_host in hosts]
        assert len(matching) == 1, (api_host, matching)
        picked = _resolve_api_base(frontend_host).replace('https://', '')
        assert picked in csp[matching[0]], (frontend_host, picked, csp[matching[0]])


if __name__ == "__main__":
    test_render_yaml_has_prod_tester_and_demo_pairs()
    test_every_frontend_routes_to_its_own_api()
    test_tester_frontend_never_routes_to_production()
    test_each_frontend_csp_allows_the_api_config_js_picks()
    print("\nAll frontend API routing tests passed.")
