import pytest

from agent_reach.backends.facebook_cloak import normalize
from agent_reach.channels.facebook import FacebookChannel
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError


def test_cards_exclude_navigation_and_preserve_identity():
    rows = [
        {'title': 'Search', 'url': 'https://www.facebook.com/search/top?q=openai'},
        {'title': 'External', 'url': 'https://facebook.com.evil.test/openai'},
        {'title': 'OpenAI', 'url': 'https://www.facebook.com/openai?tracking=secret'},
        {'title': 'OpenAI duplicate', 'url': 'https://www.facebook.com/openai?tracking=other'},
        {'title': 'One', 'url': 'https://www.facebook.com/profile.php?id=123&ref=search'},
        {'title': 'Two', 'url': 'https://www.facebook.com/profile.php?id=456&ref=search'},
    ]
    items = normalize(rows, 3)
    assert [i['url'] for i in items] == ['https://www.facebook.com/openai',
        'https://www.facebook.com/profile.php?id=123', 'https://www.facebook.com/profile.php?id=456']


def test_facebook_cloak_search_does_not_need_bridge(monkeypatch):
    ch = FacebookChannel()
    monkeypatch.setattr(ch, '_cloak_search', lambda **kw: [{'title': 'OpenAI'}])
    monkeypatch.setattr(ch, '_opencli_search', lambda **kw: pytest.fail('must use Cloak'))
    result = run_action(ch, 'search', {'query': 'OpenAI', 'limit': 1}, only_backend='cloakbrowser')
    assert result['ok'] and result['backend'] == 'cloakbrowser'


def test_facebook_risk_stops_fallback(monkeypatch):
    ch = FacebookChannel()
    def blocked(**kw):
        raise ReachError('PLATFORM_BLOCKED', 'stop')
    monkeypatch.setattr(ch, '_cloak_search', blocked)
    monkeypatch.setattr(ch, '_opencli_search', lambda **kw: pytest.fail('must stop'))
    assert run_action(ch, 'search', {'query': 'OpenAI', 'limit': 1})['error']['code'] == 'PLATFORM_BLOCKED'
