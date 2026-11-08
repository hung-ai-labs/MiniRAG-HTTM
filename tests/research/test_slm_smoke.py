"""Routing/auth guards must fail before forwarding credentials to a dashboard."""
import asyncio
import os
from pathlib import Path
import sys
from unittest.mock import patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'reproduce/research'))
import slm_smoke


@pytest.mark.parametrize('url', [
    'https://modal.com/apps/workspace/main/deployed/minirag-slm/v1',
    'https://example.modal.run/v1/v1',
    'https://user:password@example.modal.run/v1',
    'https://example.modal.run/v1?token=secret',
])
def test_invalid_routes_refused_before_network(url):
    with patch.dict(os.environ, {'MINIRAG_SLM_URL': url, 'MINIRAG_SLM_KEY': 'fixture'}), \
         patch('httpx.AsyncClient', side_effect=AssertionError('Network client created')):
        with pytest.raises(ValueError):
            asyncio.run(slm_smoke.probe({}, 1))


def test_metadata_auth_failure_never_sends_a_completion():
    requests = []
    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(401, json={'error': 'Unauthorized'})
    factory = httpx.AsyncClient
    with patch.dict(os.environ, {'MINIRAG_SLM_URL': 'https://fixture.modal.run/v1', 'MINIRAG_SLM_KEY': 'fixture'}), \
         patch('httpx.AsyncClient', side_effect=lambda **kw: factory(transport=httpx.MockTransport(reply), **kw)), \
         patch('openai.AsyncOpenAI', side_effect=AssertionError('Completion client created')):
        with pytest.raises(ValueError, match='HTTP 401'):
            asyncio.run(slm_smoke.probe({}, 1))
    assert requests == ['/version']
