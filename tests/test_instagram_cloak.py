from unittest.mock import Mock

import pytest

from agent_reach.backends import cloak, instagram_cloak
from agent_reach.channels.instagram import InstagramChannel
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError


@pytest.mark.parametrize('action,params', [('search', {'query': 'nasa'}), ('profile', {'username': 'nasa'}), ('posts', {'username': 'nasa'})])
def test_order_and_fallback(monkeypatch, action, params):
    ch = InstagramChannel()
    def missing(**kw):
        raise ReachError('NEED_SETUP', 'missing')
    monkeypatch.setattr(ch, '_cloak_' + action, missing)
    monkeypatch.setattr(ch, '_opencli_' + action, lambda **kw: [{'title': 'ok'}])
    result = run_action(ch, action, params)
    assert result['backend'] == 'opencli'
    assert [a['backend'] for a in result['meta']['attempts']] == ['cloakbrowser', 'opencli']


@pytest.mark.parametrize('code', ['NEED_LOGIN', 'RATE_LIMITED', 'PLATFORM_BLOCKED'])
def test_stop_on_final_error(monkeypatch, code):
    ch = InstagramChannel()
    def fail(**kw):
        raise ReachError(code, 'stop')
    monkeypatch.setattr(ch, '_cloak_search', fail)
    monkeypatch.setattr(ch, '_opencli_search', lambda **kw: pytest.fail('unexpected fallback'))
    assert run_action(ch, 'search', {'query': 'nasa'})['error']['code'] == code


@pytest.mark.parametrize('status,data,code', [(429, {}, 'RATE_LIMITED'), (401, {}, 'NEED_LOGIN'), (403, {}, 'PLATFORM_BLOCKED'), (200, {'message': 'challenge_required'}, 'PLATFORM_BLOCKED'), (200, None, 'UPSTREAM_BROKEN')])
def test_response_classification(status, data, code):
    page = Mock()
    page.evaluate.return_value = {'status': status, 'data': data}
    with pytest.raises(ReachError) as exc:
        instagram_cloak.fetch(page, '/fixed-path')
    assert exc.value.code == code


def test_profile_mapping_and_cookie_scope():
    page = Mock()
    page.url = 'https://www.instagram.com/'
    page.locator.return_value.is_visible.return_value = False
    page.evaluate.return_value = {'status': 200, 'data': {'data': {'user': {'username': 'nasa', 'biography': 'Space'}}}}
    items = instagram_cloak.execute(page, 'profile', {'username': '@nasa'})
    assert items[0]['text'] == 'Space'
    assert items[0]['url'] == 'https://www.instagram.com/nasa/'
    cookies = [{'domain': d, 'name': 's', 'value': 'private', 'path': '/'} for d in ['.instagram.com', '.facebook.com']]
    assert len(cloak.scoped_cookies('instagram', cookies)) == 1


def test_invalid_username_before_navigation():
    page = Mock()
    with pytest.raises(ReachError):
        instagram_cloak.execute(page, 'posts', {'username': '../accounts'})
    page.goto.assert_not_called()
