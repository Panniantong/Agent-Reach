"""Read-only session discovery and explicit connection choices. Never logs a user in."""
import json
import urllib.request
from urllib.parse import urlsplit

from agent_reach.config import Config
from agent_reach.utils.url import host_matches

from . import state
from .result import BAD_INPUT, NEED_SETUP, ReachError


def cdp_url():
    value = Config(read_only=True).get('boss_cdp_url', 'http://127.0.0.1:9222')
    return validate_cdp(value)


def validate_cdp(value):
    try:
        u = urlsplit(value)
        valid = (u.scheme == 'http' and u.hostname in {'localhost', '127.0.0.1', '::1'}
                 and u.port and not u.username and not u.password and not u.query
                 and not u.fragment and u.path in ('', '/'))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ReachError(BAD_INPUT, 'CDP must be a loopback HTTP address with an explicit port')
    return value.rstrip('/')


def cdp_status():
    url = cdp_url()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + '/json/list', timeout=2) as resp:
            tabs = json.loads(resp.read(1024 * 1024))
        found = isinstance(tabs, list) and any(
            isinstance(t, dict) and t.get('type') == 'page'
            and host_matches(t.get('url', ''), 'zhipin.com') for t in tabs)
        return {'endpoint': url, 'connected': isinstance(tabs, list), 'boss_tab_present': bool(found)}
    except (OSError, ValueError):
        return {'endpoint': url, 'connected': False, 'boss_tab_present': False}


def require_boss_cdp():
    status = cdp_status()
    if not status['connected'] or not status['boss_tab_present']:
        raise ReachError(NEED_SETUP, 'No existing BOSS page on the selected CDP endpoint',
                         hint='Run agent-reach login boss for reuse options; only --new-browser opens a dedicated browser.')
    return status['endpoint']


def bind_cdp(value):
    value = validate_cdp(value)
    Config().set('boss_cdp_url', value)
    data = state.load()
    data['checks'].pop('boss', None)
    state.save(data)
    return {'channel': 'boss', 'cdp_url': value, 'verified': False}


def profiles():
    from .browser import connected_contexts
    from .result import ReachError
    from .tools import resolve
    if not resolve('opencli'):
        return {'profiles': [], 'discovery_error': 'OpenCLI is not installed'}
    try:
        contexts = connected_contexts()
    except ReachError as exc:
        return {'profiles': [], 'discovery_error': exc.message}
    labels = Config(read_only=True).get('browser_labels', {})
    return {'profiles': [{'id': c, 'label': labels.get(c, c), 'connected': True} for c in contexts]}


def use_profile(value, label=None):
    from .browser_binding import KEY
    if value not in [p['id'] for p in profiles()['profiles']]:
        raise ReachError(NEED_SETUP, 'Selected profile is not connected; reconnect its OpenCLI extension first')
    config = Config()
    config.set('browser_default_profile', value)
    if label:
        labels = dict(config.get('browser_labels', {}))
        labels[value] = label
        config.set('browser_labels', labels)
    data = state.load()
    overrides = config.get(KEY, {})
    from agent_reach.channels import get_all_channels
    for ch in get_all_channels():
        if 'opencli' in ch.tools and ch.name not in overrides:
            data['checks'].pop(ch.name, None)
    state.save(data)
    return {'profile': value, 'scope': 'OpenCLI channels without a per-channel override', 'verified': False}


def session_plan(ch):
    """Describe transport availability separately from authentication and saved checks."""
    from agent_reach.backends.opencli import OPENCLI_EXTENSION_URL

    from .browser_binding import profile_for
    from .sessions import has_login_state
    plan = {'channel': ch.name, 'logged_in': None, 'opened_browser': False,
            'last_check': state.load()['checks'].get(ch.name),
            'verify': f'agent-reach check {ch.name} --search'}
    if 'opencli' in ch.tools:
        profile = profile_for(ch.name)
        found = profiles()
        if profile == 'dedicated':
            from . import browser
            context = browser.bound_context()
        else:
            context = profile
        connected = context is not None and context in [p['id'] for p in found['profiles']]
        plan.update({'via': 'opencli', 'profile': profile, 'connected': connected, 'extension_url': OPENCLI_EXTENSION_URL, **found,
                     'next': ('Existing browser selected. Verify first; log in there only if NEED_LOGIN.' if connected
                              else 'Choose/reconnect an existing browser: agent-reach browser profiles; agent-reach browser use CONTEXT_ID. No browser has been opened.')})
    elif ch.name == 'boss':
        status = cdp_status()
        plan.update({'via': 'cdp', **status,
                     'next': ('Existing BOSS page found. Confirm it is logged in and stable; then login boss --sync and check boss --search.'
                              if status['boss_tab_present'] else
                              'Use browser bind boss http://127.0.0.1:PORT for an existing CDP browser. Ordinary Chrome without CDP cannot be attached. Only login boss --new-browser explicitly opens the persistent dedicated profile.')})
    else:
        saved = bool(ch.session and has_login_state(ch.session))
        plan.update({'via': 'native-tool', 'saved_state_present': saved,
                     'next': 'Verify the existing tool/session first. Only use login CHANNEL --native if authentication is needed; its tool may open a browser or show a QR code.'})
    from .manage import uses_cloak
    if uses_cloak(ch):
        from agent_reach.backends.cloak import status as cloak_status
        plan['primary_backend'] = cloak_status(ch.name)
        plan['fallback_next'] = plan['next']
        plan['next'] = (f"Run agent-reach ensure {ch.name} to check the existing Cloak or connected "
                        "OpenCLI session. To authorize site-scoped import from Chrome, add "
                        "--reuse-profile ID. The user logs in only when ensure requests it.")
    return plan


def open_boss_browser():
    """Explicit opt-in only; retain profile, never close/restart a user's browser."""
    import subprocess

    from . import browser
    status = cdp_status()
    if status['connected']:
        return {**status, 'opened_browser': False, 'next': 'Use the existing window; open BOSS there if needed and confirm login.'}
    if cdp_url() != 'http://127.0.0.1:9222':
        raise ReachError(NEED_SETUP, 'Reconnect the selected CDP browser; refusing to launch a different endpoint')
    from agent_reach.utils.paths import make_private_dir
    make_private_dir(browser.profile_dir())
    subprocess.Popen([browser.ensure_chrome(), '--remote-debugging-address=127.0.0.1',
                      '--remote-debugging-port=9222', f'--user-data-dir={browser.profile_dir()}',
                      'https://www.zhipin.com/web/geek/job'], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    if not browser.wait_for(lambda: cdp_status()['connected'], 25, interval=0.5):
        raise ReachError(NEED_SETUP, 'Dedicated CDP browser did not become ready; no profile was deleted')
    return {'opened_browser': True, 'profile_reused': True, 'logged_in': None,
            'next': 'Confirm this window is logged in and stable, then agent-reach login boss --sync.'}
