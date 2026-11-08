# -*- coding: utf-8 -*-
"""Dedicated tests for the ``boss`` channel."""

from agent_reach.channels.boss import BossChannel


def test_ambiguous_upstream_detail_login_signal_is_not_a_login_instruction(monkeypatch):
    import pytest

    from agent_reach.backends import opencli
    from agent_reach.runtime.result import ReachError
    def broken(*a, **k):
        raise ReachError("NEED_LOGIN", "BOSS redirected the job detail page to the login flow")
    monkeypatch.setattr(opencli, "opencli_call", broken)
    with pytest.raises(ReachError) as exc:
        BossChannel()._opencli_read(target="https://www.zhipin.com/job_detail/job123.html", timeout=10)
    assert exc.value.code == "UPSTREAM_BROKEN"


def test_can_handle_matches_zhipin_hosts():
    ch = BossChannel()
    for url in [
        "https://www.zhipin.com/job_detail/abc.html",
        "https://zhipin.com/web/geek/job?query=大模型",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://example.com",
        "https://zhipin.com.evil.test/job",
        "",
        "https://user@zhipin.com/job",
    ]:
        assert ch.can_handle(url) is False, url


def test_native_detail_uses_browser_only_and_keeps_references_private(monkeypatch, tmp_path):
    import json
    import os
    import sys
    from types import SimpleNamespace

    from agent_reach.backends import boss_native

    source='https://github.com/can4hou6joeng4/boss-agent-cli/archive/'+boss_native.COMMIT+'.zip'
    monkeypatch.setattr(boss_native,'distribution',lambda *a:SimpleNamespace(read_text=lambda *a:json.dumps({'url':source})))
    calls=[]
    class Boss:
        def __init__(self,auth,**kwargs):
            assert kwargs['browser_source']=='existing-browser'
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def search_jobs(self,*args,**kwargs):
            return {'code':0,'zpData':{'jobList':[{'encryptJobId':'job','securityId':'private-reference','jobName':'Data'}]}}
        def job_card_browser(self,ref,lid):
            calls.append(ref)
            return {'code':0,'zpData':{'jobCard':{'postDescription':'Real JD'}}}
        def job_detail(self,*args):raise AssertionError('Independent HTTP used')
        def job_card(self,*args):raise AssertionError('Hybrid HTTP used')
    monkeypatch.setitem(sys.modules,'boss_agent_cli.api.client',SimpleNamespace(BossClient=Boss))
    monkeypatch.setitem(sys.modules,'boss_agent_cli.auth.manager',SimpleNamespace(AuthManager=lambda *a:None))
    monkeypatch.setitem(sys.modules,'boss_agent_cli.commands.detail',SimpleNamespace(
        build_job_from_card=lambda card,**k:{'description':card['postDescription'],'security_id':k['security_id']}))
    spec={'action':'search','query':'Data','limit':1,'data_dir':str(tmp_path),'cdp_url':'http://127.0.0.1:9222','session_stamp':'one'}
    monkeypatch.setattr(sys,'argv',['boss_native',json.dumps(spec)])
    result=boss_native.main()
    assert 'private-reference' not in json.dumps(result)
    path=tmp_path/'reach-job-refs.json'
    if os.name != 'nt':
        assert path.stat().st_mode & 0o077 == 0
    spec.update(action='read',job_id='job')
    monkeypatch.setattr(sys,'argv',['boss_native',json.dumps(spec)])
    result=boss_native.main()
    assert result['data'][0]['description']=='Real JD'
    assert calls==['private-reference']
    assert 'security_id' not in result['data'][0]
    spec['session_stamp']='changed-account'
    monkeypatch.setattr(sys,'argv',['boss_native',json.dumps(spec)])
    assert boss_native.main()['error']['code']=='NEED_SETUP'
    assert calls==['private-reference']
