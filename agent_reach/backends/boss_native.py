"""Subprocess entry in the pinned Boss tool's interpreter; public strict-CDP API only."""
import json
import sys
from importlib.metadata import distribution
from pathlib import Path

COMMIT = '4c991b77086a203173bf08a4cb64a23af6514fe6'


def main():
    spec = json.loads(sys.argv[1])
    dist = distribution('boss-agent-cli')
    source = json.loads(dist.read_text('direct_url.json') or '{}')
    if source.get('vcs_info', {}).get('commit_id') != COMMIT:
        return {'ok': False, 'error': {'code': 'NEED_SETUP', 'message': 'Boss dependency differs from the verified commit; run agent-reach add boss to install the pinned private tool'}}
    from boss_agent_cli.api.client import BossClient
    from boss_agent_cli.auth.manager import AuthManager
    auth = AuthManager(Path(spec['data_dir']))
    with BossClient(auth, cdp_url=spec['cdp_url'], browser_source='existing-browser') as boss:
        raw = boss.search_jobs(spec['query'], city=spec.get('city') or '全国', page=1)
    if raw.get('code') != 0:
        code = raw.get('code')
        mapped = {36: 'PLATFORM_BLOCKED', 37: 'PLATFORM_BLOCKED', 9: 'RATE_LIMITED', 1: 'NEED_LOGIN'}.get(code, 'UPSTREAM_BROKEN')
        return {'ok': False, 'error': {'code': mapped, 'message': str(raw.get('message', 'Boss search failed'))[:300]}}
    rows = raw.get('zpData', {}).get('jobList', [])
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
