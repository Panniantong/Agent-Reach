"""Local site-session reuse never navigates or modifies the source browser."""
import json

import pytest

from agent_reach.runtime import browser, cdp, cli, state
from agent_reach.runtime.result import ReachError


def test_unmanaged_debugging_port_is_never_closed_or_navigated(monkeypatch):
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(browser, "watcher_running", lambda: False)
    monkeypatch.setattr(browser, "_profile_pids", lambda: [])
    monkeypatch.setattr(cdp, "call", lambda *a, **k: pytest.fail("touched unrelated browser"))
    for operation in (browser.ensure_running, browser.stop, lambda: browser.start("https://example.com")):
        with pytest.raises(ReachError, match="unmanaged"):
            operation()



@pytest.mark.parametrize("args", [
    ["browser", "import", "xiaohongshu", "--opencli-profile", "foreign"],
    ["ensure", "xiaohongshu", "--reuse-profile", "foreign"],
    ["browser", "import", "xiaohongshu", "--state-file", "private.json"],
])
def test_retired_raw_import_flags_are_not_accepted(args, monkeypatch, capsys):
    monkeypatch.setattr(browser, "ensure_running", lambda: pytest.fail("opened browser"))
    monkeypatch.setattr(cdp, "call", lambda *a, **k: pytest.fail("read credentials"))
    assert cli.main(args) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "BAD_INPUT"
    assert not state.load().get("reuse_sources")


def test_local_site_export_uses_the_unmodified_upstream_page_api(monkeypatch):
    from unittest.mock import Mock

    from agent_reach.backends import opencli
    from agent_reach.runtime import bridge, run
    source = state.root() / "upstream/dist/src/daemon.js"
    module = source.parent / "browser/page.js"
    module.parent.mkdir(parents=True)
    module.write_text("// official API fixture")
    monkeypatch.setattr(bridge, "launch_spec", lambda: (["node", str(source)], "1.8.7"))
    command = Mock(return_value="[]")
    monkeypatch.setattr(run, "run_cmd", command)
    assert opencli.export_site_cookies("local", "xiaohongshu.com") == []
    args = command.call_args.args[0]
    assert module.as_uri() in args[3] and args[-2:] == ["local", "xiaohongshu.com"]
    assert module.read_text() == "// official API fixture"


def test_site_export_reports_a_missing_bridge_without_reading_cookies(monkeypatch):
    from agent_reach.backends import opencli
    from agent_reach.runtime import bridge, run

    monkeypatch.setattr(bridge, "status", lambda: {})
    monkeypatch.setattr(run, "run_cmd", lambda *a, **k: pytest.fail("read cookies without a Bridge"))

    with pytest.raises(ReachError) as caught:
        opencli.export_site_cookies("local", "xiaohongshu.com")

    assert caught.value.code == "NEED_SETUP"
    assert "Bridge" in caught.value.message
    assert "agent-reach browser setup" in caught.value.hint


def test_automatic_reuse_copies_only_the_requested_site_and_reuses_cache(monkeypatch):
    from unittest.mock import Mock

    from agent_reach.backends import opencli
    from agent_reach.runtime import session_reuse
    monkeypatch.setattr(browser, 'ensure_running', lambda: None)
    monkeypatch.setattr(browser, 'connected_contexts', lambda: ['daily', 'owned'])
    monkeypatch.setattr(browser, 'bound_context', lambda: 'owned')
    export = Mock(return_value=[{'name':'sid','value':'test','domain':'.xiaohongshu.com','expirationDate':9999999999,'sameSite':'lax'},
                                {'name':'foreign','value':'never-copy','domain':'other.test'},
                                {'name':'expired','value':'never-copy','domain':'.xiaohongshu.com','expirationDate':1}])
    monkeypatch.setattr(opencli, 'export_site_cookies', export)
    calls=[]
    monkeypatch.setattr(cdp, 'call', lambda method, params=None: calls.append((method,params)) or {})
    result=session_reuse.prepare('xiaohongshu')
    assert result['copied_cookies']==1 and not result['verified'] and not result['source_changed']
    cookie=next(params['cookies'][0]for method,params in calls if method=='Storage.setCookies')
    assert cookie['name']=='sid' and cookie['sameSite']=='Lax' and cookie['expires']==9999999999
    assert session_reuse.prepare('xiaohongshu')==result
    export.assert_called_once_with('daily','xiaohongshu.com')


@pytest.mark.parametrize("bridge_available", [True, False])
def test_saved_import_survives_an_hour_without_rereading_the_source(monkeypatch, bridge_available):
    from agent_reach.runtime import bridge, session_reuse

    saved = {'source': 'daily', 'copied_cookies': 1, 'cookie_snapshot': 1,
             'at': '2020-01-01T00:00:00Z'}
    state.mutate(lambda data: data.setdefault('session_reuse', {}).__setitem__('xiaohongshu', saved))
    monkeypatch.setattr(browser, 'ensure_running', lambda: None)
    if not bridge_available:
        monkeypatch.setattr(bridge, "status", lambda: {})
    monkeypatch.setattr(session_reuse, '_source_cookies',
                        lambda *a: pytest.fail('reread the source just because time passed'))
    monkeypatch.setattr(cdp, 'call', lambda *a, **k: pytest.fail('overwrote the saved session'))

    assert session_reuse.prepare('xiaohongshu') == saved


def test_explicit_import_can_refresh_a_saved_snapshot(monkeypatch):
    from unittest.mock import Mock

    from agent_reach.runtime import session_reuse

    saved = {'source': 'daily', 'copied_cookies': 1, 'cookie_snapshot': 1, 'at': state.now()}
    state.mutate(lambda data: data.setdefault('session_reuse', {}).__setitem__('xiaohongshu', saved))
    incoming = [{'name': 'sid', 'value': 'refreshed', 'domain': '.xiaohongshu.com', 'path': '/'}]
    source = Mock(return_value=(incoming, 'daily'))
    call = Mock(return_value={})
    monkeypatch.setattr(browser, 'ensure_running', lambda: None)
    monkeypatch.setattr(browser, 'save_session', lambda: None)
    monkeypatch.setattr(session_reuse, '_source_cookies', source)
    monkeypatch.setattr(cdp, 'call', call)

    result = session_reuse.prepare('xiaohongshu', force=True)

    source.assert_called_once_with('xiaohongshu', ['xiaohongshu.com'])
    call.assert_any_call('Storage.setCookies', {'cookies': incoming})
    assert result['copied_cookies'] == 1 and result['cookie_snapshot'] == 1


def test_multiple_local_accounts_are_not_guessed(monkeypatch):
    from agent_reach.backends import opencli
    from agent_reach.runtime import session_reuse
    monkeypatch.setattr(browser,'ensure_running',lambda:None)
    monkeypatch.setattr(browser,'connected_contexts',lambda:['one','two'])
    monkeypatch.setattr(opencli,'export_site_cookies',lambda *args:[{'name':'sid','value':'test','domain':'.xiaohongshu.com'}])
    monkeypatch.setattr(cdp,'call',lambda *a,**k:pytest.fail('ambiguous account copied'))
    with pytest.raises(ReachError,match='Several'):
        session_reuse.prepare('xiaohongshu')


def test_logout_blocks_automatic_session_revival(monkeypatch):
    from agent_reach.runtime import session_reuse
    monkeypatch.setattr(browser,'ensure_running',lambda:None)
    state.mutate(lambda data:data.update(session_reuse={'xiaohongshu':{'blocked':True}}))
    monkeypatch.setattr(session_reuse,'_source_cookies',lambda *a:pytest.fail('revived logged-out account'))
    assert session_reuse.prepare('xiaohongshu')['blocked']


def test_selecting_another_source_keeps_explicit_logout_and_manual_login(monkeypatch):
    from agent_reach.runtime import session_reuse
    monkeypatch.setattr(browser,'bound_context',lambda:'owned')
    monkeypatch.setattr(browser,'connected_contexts',lambda:['daily','owned'])
    state.mutate(lambda data:data.update(session_reuse={
        'xiaohongshu':{'blocked':True},'bilibili':{'source':'manual'},'reddit':{'source':'previous','copied_cookies':10}}))
    session_reuse.use('daily')
    saved=state.load()
    assert saved['local_browser_source']=='daily'
    assert saved['session_reuse']['xiaohongshu']['blocked']
    assert saved['session_reuse']['bilibili']['source']=='manual'
    assert 'reddit'not in saved['session_reuse']


def test_unavailable_source_keeps_saved_destination_and_does_not_open_login(monkeypatch):
    from agent_reach.runtime import session_reuse
    monkeypatch.setattr(browser,'ensure_running',lambda:None)
    monkeypatch.setattr(browser,'connected_contexts',lambda:[])
    monkeypatch.setattr(browser,'start',lambda *a:pytest.fail('opened a login window'))
    monkeypatch.setattr(cdp,'call',lambda *a,**k:pytest.fail('changed saved session'))
    result=session_reuse.prepare('xiaohongshu')
    assert result['source']=='saved-profile' and result['copied_cookies']==0


def test_explicit_import_without_a_source_login_fails_and_keeps_saved_state(monkeypatch):
    from agent_reach.runtime import bridge, session_reuse
    saved = {'source': 'daily', 'copied_cookies': 3, 'cookie_snapshot': 1, 'at': state.now()}
    state.mutate(lambda data: data.setdefault('session_reuse', {}).__setitem__('xiaohongshu', saved))
    monkeypatch.setattr(browser, 'ensure_running', lambda: None)
    monkeypatch.setattr(bridge, 'require_running', lambda: {'ok': True})
    monkeypatch.setattr(session_reuse, '_source_cookies', lambda *a: ([], 'saved-profile'))
    monkeypatch.setattr(cdp, 'call', lambda *a, **k: pytest.fail('changed saved session'))
    with pytest.raises(ReachError) as caught:
        session_reuse.prepare('xiaohongshu', force=True)
    assert caught.value.code == 'NEED_SETUP'
    assert state.load()['session_reuse']['xiaohongshu'] == saved


def test_missing_bridge_is_not_recorded_as_an_empty_site_session(monkeypatch):
    from agent_reach.runtime import bridge, session_reuse

    monkeypatch.setattr(browser, "ensure_running", lambda: None)
    monkeypatch.setattr(bridge, "status", lambda: {})
    monkeypatch.setattr(cdp, "call", lambda *a, **k: pytest.fail("changed saved session"))

    with pytest.raises(ReachError) as caught:
        session_reuse.prepare("xiaohongshu")

    assert caught.value.code == "NEED_SETUP"
    assert "Bridge" in caught.value.message
    assert "agent-reach browser setup" in caught.value.hint
    assert "xiaohongshu" not in state.load().get("session_reuse", {})


def test_site_snapshot_expires_destination_only_cookies_and_preserves_other_sites(monkeypatch):
    from agent_reach.runtime import session_reuse
    monkeypatch.setattr(browser,'ensure_running',lambda:None)
    monkeypatch.setattr(browser,'save_session',lambda:None)
    incoming=[{'name':'sid','value':'chosen','domain':'.xiaohongshu.com','path':'/'}]
    monkeypatch.setattr(session_reuse,'_source_cookies',lambda *a:(incoming,'daily'))
    jar=[{'name':'old_account','value':'stale','domain':'.xiaohongshu.com','path':'/'},
         {'name':'sid','value':'other-account','domain':'.xiaohongshu.com','path':'/'},
         {'name':'other_site','value':'keep','domain':'.other.test','path':'/'}]
    applied=[]
    def call(method,params=None):
        if method=='Storage.getCookies':
            return {'cookies':jar}
        if method=='Storage.setCookies':
            applied.extend(params['cookies'])
        return {}
    monkeypatch.setattr(cdp,'call',call)
    out=session_reuse.prepare('xiaohongshu')
    assert out['cookie_snapshot']==1
    assert any(c['name']=='old_account'and c['expires']==1 for c in applied)
    assert not any(c['name']=='other_site'for c in applied)
    assert not any(c['name']=='sid'and c.get('expires')==1 for c in applied)


def test_site_import_failure_restores_previous_site_and_retains_saved_snapshot(monkeypatch):
    from agent_reach.runtime import session_reuse
    monkeypatch.setattr(browser,'ensure_running',lambda:None)
    monkeypatch.setattr(browser,'save_session',lambda:pytest.fail('saved a failed import'))
    monkeypatch.setattr(session_reuse,'_source_cookies',lambda *a:([{'name':'new','value':'incoming','domain':'.xiaohongshu.com'}],'daily'))
    calls=[]
    def call(method,params=None):
        if method=='Storage.getCookies':
            return {'cookies':[{'name':'old','value':'saved','domain':'.xiaohongshu.com'}]}
        calls.append(params['cookies'])
        return None if len(calls)==1 else {}
    monkeypatch.setattr(cdp,'call',call)
    with pytest.raises(ReachError,match='saved state retained'):
        session_reuse.prepare('xiaohongshu')
    assert any(c['name']=='old'and c['value']=='saved'for c in calls[1])
    assert any(c['name']=='new'and c['expires']==1 for c in calls[1])


def test_dispatch_worker_reuses_session_without_relocking_the_calling_thread(monkeypatch):
    from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
    from agent_reach.runtime import dispatch, run, session_reuse
    monkeypatch.setattr(browser, 'ensure_running', lambda: None)
    monkeypatch.setattr(browser, 'bound_context', lambda: 'owned')
    monkeypatch.setattr(browser, 'save_session', lambda: None)
    monkeypatch.setattr(session_reuse, '_source_cookies', lambda *a: ([], 'saved-profile'))
    monkeypatch.setattr(run, 'run_cmd', lambda *a, **k: '[{"title":"real result shape"}]')
    result=dispatch.run_action(XiaoHongShuChannel(), 'search', {'query':'test','limit':1}, timeout=2)
    assert result['ok'], result.get('error')


def test_dispatch_reports_missing_bridge_before_calling_the_site_backend(monkeypatch):
    from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
    from agent_reach.runtime import bridge, dispatch, run

    monkeypatch.setattr(browser, "ensure_running", lambda: None)
    monkeypatch.setattr(browser, "bound_context", lambda: "owned")
    monkeypatch.setattr(bridge, "status", lambda: {})
    monkeypatch.setattr(run, "run_cmd", lambda *a, **k: pytest.fail("called the site without a Bridge"))

    result = dispatch.run_action(XiaoHongShuChannel(), "search", {"query": "test", "limit": 1},
                                 timeout=2, only_backend="opencli")

    assert not result["ok"]
    assert result["error"]["code"] == "NEED_SETUP"
    assert "agent-reach browser setup" in result["error"]["hint"]
    assert result["meta"]["attempts"][0]["result"] == "NEED_SETUP"
    assert "xiaohongshu" not in state.load().get("session_reuse", {})
    health = state.load()["backend_health"]["xiaohongshu"]["search"]["opencli"]
    assert health["code"] == "NEED_SETUP"


def test_bili_reuses_only_site_cookies_through_upstream_writer_and_private_stdin(monkeypatch):
    from pathlib import Path
    from unittest.mock import Mock

    from agent_reach.channels import bilibili
    from agent_reach.runtime import session_reuse, tools
    monkeypatch.setattr(session_reuse, '_source_cookies', lambda *a: ([{'name':'SESSDATA','value':'test-secret'}], 'daily'))
    monkeypatch.setattr(tools,'resolve',lambda *a:'/private/bin/bili')
    call=Mock(return_value='')
    monkeypatch.setattr(bilibili,'run_cmd',call)
    bilibili._reuse_subtitle_login(10)
    args=call.call_args
    assert 'test-secret' not in repr(args.args)
    assert json.loads(args.kwargs['input_data']) == {'SESSDATA':'test-secret'}
    assert 'save_credential' in args.args[0][-1]
    assert Path(args.kwargs['env']['HOME']) == state.root() / 'sessions' / 'bili-cli'
    state.mutate(lambda data: data['session_reuse'].__setitem__('bilibili', {'blocked':True}))
    bilibili._reuse_subtitle_login(10)
    assert call.call_count == 1


def test_native_bili_subtitles_do_not_require_an_optional_browser_bridge(monkeypatch):
    from agent_reach.channels import bilibili
    monkeypatch.setattr(browser,'connected_contexts',lambda:(_ for _ in()).throw(ReachError('NEED_SETUP','OpenCLI is not installed')))
    monkeypatch.setattr(bilibili,'run_cmd',lambda *a,**k:pytest.fail('started optional browser integration'))
    monkeypatch.setattr(bilibili,'_bili_json',lambda *a:{'subtitle':{'available':True,'text':'Saved native login works'},'video':{'bvid':'BV1Jgf6YvE8e'}})
    out=bilibili.BilibiliChannel()._cli_subtitle(target='BV1Jgf6YvE8e',timeout=2)
    assert out[0]['text']=='Saved native login works'


def test_node_warning_does_not_hide_upstream_error_and_404_is_not_login():
    from agent_reach.backends.opencli import _opencli_error
    warning='(node:123) Warning: experimental proxy\n'
    error=_opencli_error(warning+'ok: false\nerror:\n  code: UNKNOWN\n  message: HTTP 404 - make sure you are logged in to Instagram\n','login')
    assert error.code=='UPSTREAM_BROKEN'
    assert '(node:' not in error.message
    assert _opencli_error(warning+'ok: false\nerror:\n  code: AUTH_REQUIRED\n  message: Login required\n','login').code=='NEED_LOGIN'


def test_xueqiu_syncs_reused_browser_login_only_for_community_actions(monkeypatch):
    from unittest.mock import Mock

    from agent_reach.channels import xueqiu
    from agent_reach.runtime import session_reuse
    reuse=Mock()
    sync=Mock()
    monkeypatch.setattr(session_reuse,'prepare',reuse)
    monkeypatch.setattr(xueqiu,'_import_from_browser',sync)
    monkeypatch.setattr(xueqiu,'_xq_json',lambda *a:{})
    ch=xueqiu.XueqiuChannel()
    ch._xq_search(query='AAPL',limit=2,timeout=2)
    reuse.assert_not_called()
    ch._xq_hot_posts(limit=2,timeout=2)
    reuse.assert_called_once_with('xueqiu')
    sync.assert_called_once_with()
