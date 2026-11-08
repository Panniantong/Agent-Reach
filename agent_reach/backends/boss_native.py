"""Subprocess entry in the pinned Boss tool's interpreter; public strict-CDP API only."""
import json
import os
import sys
import tempfile
import time
from importlib.metadata import distribution
from pathlib import Path

COMMIT = '4c991b77086a203173bf08a4cb64a23af6514fe6'


def main():
    spec = json.loads(sys.argv[1])
    dist = distribution('boss-agent-cli')
    source = json.loads(dist.read_text('direct_url.json') or '{}')
    archive = f'https://github.com/can4hou6joeng4/boss-agent-cli/archive/{COMMIT}.zip'
    if source.get('vcs_info', {}).get('commit_id') != COMMIT and source.get('url') != archive:
        return {'ok': False, 'error': {'code': 'NEED_SETUP', 'message': 'Boss dependency differs from the verified commit; run agent-reach add boss to install the pinned private tool'}}
    from boss_agent_cli.api.client import BossClient
    from boss_agent_cli.auth.manager import AuthManager
    auth = AuthManager(Path(spec['data_dir']))
    refs = Path(spec['data_dir']) / 'reach-job-refs.json'
    if refs.is_symlink():
        return {'ok': False, 'error': {'code': 'NEED_SETUP', 'message': 'Unmanaged job-reference path; left untouched'}}
    with BossClient(auth, cdp_url=spec['cdp_url'], browser_source='existing-browser') as boss:
        if spec['action'] == 'read':
            try:
                saved = json.loads(refs.read_text())
                ref = saved['jobs'][spec['job_id']]
                if time.time() - saved['at'] > 3600 or saved.get('session_stamp') != spec.get('session_stamp'):
                    raise KeyError('expired')
            except (OSError, ValueError, KeyError, TypeError):
                return {'ok': False, 'error': {'code': 'NEED_SETUP', 'message': 'No recent search reference; use the job link returned by a fresh search'}}
            # Public upstream API, explicitly browser-only. Never job_detail()
            # or job_card(), both of which can create an independent HTTP session.
            raw = boss.job_card_browser(ref['security_id'], ref.get('lid', ''))
        else:
            raw = boss.search_jobs(spec['query'], city=spec.get('city') or '全国', page=1)
    if raw.get('code') != 0:
        code = raw.get('code')
        mapped = {36: 'PLATFORM_BLOCKED', 37: 'PLATFORM_BLOCKED', 9: 'RATE_LIMITED', 1: 'NEED_LOGIN'}.get(code, 'UPSTREAM_BROKEN')
        return {'ok': False, 'error': {'code': mapped, 'message': str(raw.get('message', 'Boss search failed'))[:300]}}
    if spec['action'] == 'read':
        from boss_agent_cli.commands.detail import build_job_from_card
        card = raw.get('zpData', {}).get('jobCard') or {}
        if not card.get('postDescription'):
            return {'ok': False, 'error': {'code': 'UPSTREAM_BROKEN', 'message': 'Upstream job card did not return a JD'}}
        row = build_job_from_card(card, security_id='', greeted=False)
        row.pop('security_id', None)
        row['job_id'] = spec['job_id']
        return {'ok': True, 'data': [row]}
    rows = raw.get('zpData', {}).get('jobList', [])[:spec['limit']]
    # Short-lived upstream references stay private; no securityId/lid is exposed
    # in results, command arguments, or the model context.
    content = {'at': time.time(), 'session_stamp': spec.get('session_stamp'),
               'jobs': {r['encryptJobId']: {'security_id': r['securityId'], 'lid': r.get('lid', '')}
               for r in rows if r.get('encryptJobId') and r.get('securityId')}}
    fd, tmp = tempfile.mkstemp(dir=refs.parent, prefix='.reach-job-refs-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(content, stream)
        os.replace(tmp, refs)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    # Do not export securityId/lid or raw browser credentials in unified results.
    return {'ok': True, 'data': [{'title': r.get('jobName'), 'company': r.get('brandName'),
                                'salary': r.get('salaryDesc'), 'city': r.get('cityName'),
                                'experience': r.get('jobExperience'), 'education': r.get('jobDegree'),
                                'job_id': r.get('encryptJobId')} for r in rows[:spec['limit']]]}


if __name__ == '__main__':
    try:
        result = main()
    except Exception as exc:
        name = type(exc).__name__
        code = {'AccountRiskError': 'PLATFORM_BLOCKED', 'EnvironmentRiskError': 'PLATFORM_BLOCKED',
                'AuthRequired': 'NEED_LOGIN', 'AuthExpired': 'NEED_LOGIN',
                'BrowserSourceUnavailable': 'NEED_SETUP'}.get(name, 'UPSTREAM_BROKEN')
        result = {'ok': False, 'error': {'code': code, 'message': str(exc)[:300]}}
    print(json.dumps(result, ensure_ascii=False))
