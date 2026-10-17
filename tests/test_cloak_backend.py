"""Cloak routing, credential scope, and error boundaries without network access."""
import json

import pytest

from agent_reach.backends import cloak
from agent_reach.backends.cloak_worker import search_url, target_url
from agent_reach.channels.boss import BossChannel
from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError


@pytest.mark.parametrize('channel,params', [('boss', {'query':'data','city':'深圳','limit':2}),
                                           ('xiaohongshu', {'query':'VLA','limit':2})])
def test_cloak_first_opencli_fallback(monkeypatch, channel, params):
    ch = BossChannel() if channel == 'boss' else XiaoHongShuChannel()
    def missing(**kw):
        raise ReachError('NEED_SETUP', 'not configured')
    monkeypatch.setattr(ch, '_cloak_search', missing)
    monkeypatch.setattr(ch, '_opencli_search', lambda **kw: [{'title':'ok'}])
    out = run_action(ch, 'search', params)
    assert out['ok'] and out['backend'] == 'opencli'
    assert [x['backend'] for x in out['meta']['attempts']] == ['cloakbrowser','opencli']


@pytest.mark.parametrize('code', ['NEED_LOGIN','RATE_LIMITED','PLATFORM_BLOCKED','BUSY'])
def test_no_switch_on_identity_or_site_failure(monkeypatch, code):
    ch = XiaoHongShuChannel()
    def fail(**kw):
        raise ReachError(code, 'stop')
    monkeypatch.setattr(ch, '_cloak_search', fail)
    monkeypatch.setattr(ch, '_opencli_search', lambda **kw: pytest.fail('must not switch'))
    out = run_action(ch,'search',{'query':'VLA'})
    assert out['error']['code'] == code
    assert len(out['meta']['attempts']) == 1


def test_explicit_backend_skips_cloak(monkeypatch):
    ch = XiaoHongShuChannel()
    monkeypatch.setattr(ch, '_cloak_search', lambda **kw: pytest.fail('must skip'))
    monkeypatch.setattr(ch, '_opencli_search', lambda **kw: [])
    assert run_action(ch,'search',{'query':'VLA'},only_backend='opencli')['ok']


def test_cookie_scope_and_normalization():
    rows = [{'domain':d,'name':'session','value':'secret','path':'/','sameSite':'no_restriction'}
            for d in ['.zhipin.com','zhipin.com.evil.test','.xiaohongshu.com']]
    got = cloak.scoped_cookies('boss', rows)
    assert len(got) == 1 and got[0]['domain'] == '.zhipin.com'
    assert got[0]['sameSite'] == 'None'


@pytest.mark.parametrize('same_site', [None, 'unspecified'])
def test_missing_samesite_does_not_become_none(same_site):
    cookie = {'domain': '.zhipin.com', 'name': 'session', 'value': 'secret',
              'path': '/', 'secure': False, 'sameSite': same_site}
    got = cloak.scoped_cookies('boss', [cookie])[0]
    assert 'sameSite' not in got
    assert got['secure'] is False


@pytest.mark.parametrize('target', ['https://www.zhipin.com.evil.test/job_detail/x.html',
                                    'https://user@www.zhipin.com/job_detail/x.html',
                                    'http://www.zhipin.com/job_detail/x.html',
                                    'https://www.zhipin.com:8443/job_detail/x.html',
                                    'https://www.zhipin.com/'])
def test_read_target_boundary(target):
    with pytest.raises(ReachError):
        target_url('boss',target)


def test_city_does_not_silently_default():
    assert '101280600' in search_url('boss', {'query':'数据','city':'深圳'})
    with pytest.raises(ReachError):
        search_url('boss', {'query':'数据','city':'typo'})


def test_unconfigured_does_not_start_process(monkeypatch,tmp_path):
    monkeypatch.setenv('HOME',str(tmp_path))
    from agent_reach.runtime import run, tools
    monkeypatch.setattr(tools,'resolve',lambda _: '/fake/cloakbrowser')
    monkeypatch.setattr(run,'run_cmd',lambda *a,**k: pytest.fail('must not launch'))
    with pytest.raises(ReachError,match='cloak setup'):
        cloak.call('boss','search',query='data',timeout=30)


def test_native_login_needs_no_opencli(monkeypatch, tmp_path):
    from agent_reach.runtime import tools
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(tools, 'resolve', lambda name: pytest.fail('login must not resolve OpenCLI'))
    calls = []
    monkeypatch.setattr(cloak, 'call', lambda *a, **kw: calls.append((a, kw)) or [{'identity_verified': False}])
    result = cloak.login('instagram')
    assert calls[0][0] == ('instagram', 'login')
    assert result['logged_in'] is None
    assert json.loads((cloak.folder('instagram')/'configured.json').read_text())['source'] == 'native login'


def test_native_login_timeout_explains_window_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(cloak, 'call', lambda *a, **kw: (_ for _ in ()).throw(ReachError('TIMEOUT', 'worker timeout')))
    with pytest.raises(ReachError) as caught:
        cloak.login('xiaohongshu')
    assert caught.value.code == 'TIMEOUT'
    assert '15 minutes' in caught.value.message
    assert 'do not retry automatically' in caught.value.message
    assert not (cloak.folder('xiaohongshu') / 'configured.json').exists()


def test_import_removes_staging_file_after_failure(monkeypatch,tmp_path):
    monkeypatch.setenv('HOME',str(tmp_path))
    source=tmp_path/'cookies.json'
    source.write_text(json.dumps([{'domain':'.zhipin.com','path':'/','name':'s','value':'SECRET'}]))
    def fail(*a,**kw):
        assert 'SECRET' not in str(kw)
        raise ReachError('NEED_LOGIN','expired')
    monkeypatch.setattr(cloak,'call',fail)
    with pytest.raises(ReachError):
        cloak.import_login('boss',state_file=source)
    assert not list(cloak.folder('boss').glob('import-*.json'))
    assert not (cloak.folder('boss')/'configured.json').exists()


@pytest.mark.parametrize('layout', ['dist/src/browser/page.js', 'browser/page.js'])
def test_bridge_import_package_layout(monkeypatch, tmp_path, layout):
    from agent_reach.runtime import opencli_compat, run, tools
    monkeypatch.setenv('HOME', str(tmp_path))
    module = tmp_path / 'package' / layout
    module.parent.mkdir(parents=True)
    module.write_text('')
    monkeypatch.setattr(tools, 'resolve', lambda _: '/fake/opencli.cmd')
    monkeypatch.setattr(opencli_compat, 'package_root', lambda: tmp_path / 'package')
    def bridge(argv, **kwargs):
        assert module.as_uri() in argv[-1]
        assert 'chosen-context' in argv[-1]
        return json.dumps([{'domain':'.instagram.com', 'name':'s', 'value':'SECRET', 'path':'/'}])
    monkeypatch.setattr(run, 'run_cmd', bridge)
    def staged_import(*args, **kwargs):
        kwargs['profile_dir'].mkdir()
        return [{'access_verified': True}]
    monkeypatch.setattr(cloak, 'call', staged_import)
    result = cloak.import_login('instagram', opencli_profile='chosen-context')
    assert result['imported_cookies'] == 1
    assert not list(cloak.folder('instagram').glob('import-*.json'))
    assert (cloak.folder('instagram') / 'profile').is_dir()


def test_failed_import_preserves_previous_profile(monkeypatch, tmp_path):
    from agent_reach.runtime.result import ReachError

    path = cloak.folder('boss')
    profile = path / 'profile'
    profile.mkdir(parents=True)
    (profile / 'old-state').write_text('keep')
    source = tmp_path / 'cookies.json'
    source.write_text(json.dumps([{'domain': '.zhipin.com', 'name': 's',
                                   'value': 'private', 'path': '/'}]))
    def fail(*args, **kwargs):
        raise ReachError('NEED_LOGIN', 'source is expired')
    monkeypatch.setattr(cloak, 'call', fail)
    with pytest.raises(ReachError):
        cloak.import_login('boss', state_file=str(source))
    assert (profile / 'old-state').read_text() == 'keep'
    assert not list(path.glob('stage-*'))


def test_native_login_keeps_window_alive_and_uses_own_profile(monkeypatch, tmp_path):
    import sys
    import types

    from agent_reach.backends import cloak_worker
    binary = tmp_path / 'chrome'
    binary.touch()
    calls = []
    class Page:
        def close(self):
            assert len(ctx.pages) > 1, 'closing last tab exits headed Chrome'
            ctx.pages.remove(self)
        def goto(self, url, **kw):
            assert url == 'https://www.instagram.com'
        def wait_for_timeout(self, ms):
            ctx.pages.clear()  # user closes the login window
    class Context:
        def __init__(self):
            self.pages = [Page()]
        def new_page(self):
            p = Page()
            self.pages.append(p)
            return p
        def close(self):
            calls.append('closed')
    ctx = Context()
    def launch(profile, **kw):
        assert profile == str(tmp_path / 'own-profile')
        assert kw['headless'] is False
        assert kw['proxy'] == 'http://127.0.0.1:7897'
        return ctx
    monkeypatch.setitem(sys.modules, 'cloakbrowser', types.SimpleNamespace(launch_persistent_context=launch))
    monkeypatch.setitem(sys.modules, 'cloakbrowser.config', types.SimpleNamespace(
        PLATFORM_CHROMIUM_VERSIONS={'win': 'test'}, get_platform_tag=lambda: 'win', get_binary_path=lambda _: binary))
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', types.SimpleNamespace(Error=RuntimeError))
    monkeypatch.setenv('REACH_CLOAK_PROXY', 'http://127.0.0.1:7897')
    result = cloak_worker.execute({'channel': 'instagram', 'action': 'login', 'profile': str(tmp_path/'own-profile')})
    assert result == [{'session_saved': True, 'identity_verified': False}]
    assert calls == ['closed']


def test_proxy_override_is_per_process(monkeypatch, tmp_path):
    import os

    from agent_reach.runtime import run, tools
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('REACH_CLOAK_PROXY', 'http://127.0.0.1:17897')
    exe = tmp_path / 'tool' / 'cloakbrowser'
    exe.parent.mkdir()
    (exe.parent / ('python.exe' if os.name == 'nt' else 'python')).touch()
    monkeypatch.setattr(tools, 'resolve', lambda _: str(exe))
    profile = cloak.folder('boss')
    profile.mkdir(parents=True)
    (profile / 'configured.json').write_text('{}')
    def execute(argv, **kw):
        assert kw['env']['REACH_CLOAK_PROXY'] == 'http://127.0.0.1:17897'
        assert '17897' not in str(argv)
        return '{"items":[]}'
    monkeypatch.setattr(run, 'run_cmd', execute)
    assert cloak.call('boss', 'search', query='data', timeout=30) == []
