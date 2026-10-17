"""Instagram read actions in a Cloak-owned page, using same-origin endpoints."""
import re
from urllib.parse import urlencode, urlsplit

from agent_reach.runtime.result import ReachError, make_item


def validate(action, params):
    if action in {'profile', 'posts'}:
        name = params.get('username', '').lstrip('@')
        if not re.fullmatch(r'[A-Za-z0-9_.]{1,30}', name):
            raise ReachError('BAD_INPUT', 'Expected an Instagram username')
    if action in {'search', 'posts'}:
        limit = params.get('limit', 5)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ReachError('BAD_INPUT', 'limit must be between 1 and 100')


def fetch(page, path, *, missing_is_not_found=False):
    result = page.evaluate('''async path => {
        const response = await fetch(path, {credentials:'include',
            headers:{'X-IG-App-ID':'936619743392459'}, signal:AbortSignal.timeout(15000)});
        let data; try { data = await response.json(); } catch { data = null; }
        return {status:response.status, data};
    }''', path)
    status, data = result['status'], result.get('data')
    message = str(data.get('message', '')).lower() if isinstance(data, dict) else ''
    if status == 429:
        raise ReachError('RATE_LIMITED', 'Instagram API returned HTTP 429')
    if 'please wait' in message:
        raise ReachError('RATE_LIMITED', 'Instagram asked this session to wait')
    if isinstance(data, dict) and (data.get('challenge') or any(x in message for x in ('challenge', 'checkpoint', 'feedback_required'))):
        raise ReachError('PLATFORM_BLOCKED', 'Instagram verification required')
    if status == 401 or 'login_required' in message:
        raise ReachError('NEED_LOGIN', 'Instagram login required; import fresh site cookies')
    if status == 403:
        raise ReachError('PLATFORM_BLOCKED', 'Instagram denied this request')
    if status == 404:
        raise ReachError('NOT_FOUND' if missing_is_not_found else 'UPSTREAM_BROKEN',
                         'Instagram user or content not found' if missing_is_not_found
                         else 'Instagram endpoint changed (HTTP 404)')
    if status != 200 or not isinstance(data, dict) or data.get('status') == 'fail':
        raise ReachError('UPSTREAM_BROKEN', 'Instagram response unavailable or malformed')
    return data


def execute(page, action, params):
    from agent_reach.backends.cloak_worker import search_url
    validate(action, params)
    response = page.goto('https://www.instagram.com/', wait_until='domcontentloaded', timeout=25000)
    if response and response.status == 429:
        raise ReachError('RATE_LIMITED', 'Instagram homepage returned HTTP 429')
    path = urlsplit(page.url).path
    if path.startswith(('/challenge', '/checkpoint')):
        raise ReachError('PLATFORM_BLOCKED', 'Instagram verification required')
    if path.startswith('/accounts/login') or page.locator('input[name="password"]').is_visible():
        raise ReachError('NEED_LOGIN', 'Instagram login required; import fresh site cookies')
    limit = params.get('limit', 5)
    if action == 'search':
        url = search_url('instagram', params)
        parsed = urlsplit(url)
        data = fetch(page, parsed.path + '?' + parsed.query)
        rows = data.get('users')
        if not isinstance(rows, list):
            raise ReachError('UPSTREAM_BROKEN', 'Instagram user search schema changed')
        users = [row.get('user') for row in rows[:limit] if isinstance(row, dict)]
    else:
        username = params['username'].lstrip('@')
        if action == 'posts':
            data = fetch(page, '/api/v1/feed/user/' + username + '/username/?' + urlencode({'count': limit}),
                         missing_is_not_found=True)
            rows = data.get('items')
            if not isinstance(rows, list):
                raise ReachError('UPSTREAM_BROKEN', 'Instagram posts schema changed')
            items = []
            for row in rows[:limit]:
                if not isinstance(row, dict) or not re.fullmatch(r'[A-Za-z0-9_-]+', str(row.get('code', ''))):
                    raise ReachError('UPSTREAM_BROKEN', 'Instagram post identifier missing')
                caption = (row.get('caption') or {}).get('text', '')
                items.append(make_item(title=caption[:100] or 'Instagram post',
                    url='https://www.instagram.com/p/' + row['code'] + '/', author=username, text=caption,
                    raw={'likes': row.get('like_count'), 'comments': row.get('comment_count'),
                         'media_type': row.get('media_type'), 'content_scope': 'caption',
                         'images_read': False, 'video_read': False}))
            return items
        data = fetch(page, '/api/v1/users/web_profile_info/?' + urlencode({'username': username}),
                     missing_is_not_found=True)
        users = [(data.get('data') or {}).get('user')]
    items = []
    for user in users:
        if not isinstance(user, dict) or not re.fullmatch(r'[A-Za-z0-9_.]{1,30}', str(user.get('username', ''))):
            raise ReachError('UPSTREAM_BROKEN', 'Instagram user schema changed')
        name = user['username']
        items.append(make_item(title=user.get('full_name') or name,
            url='https://www.instagram.com/' + name + '/', author=name, text=user.get('biography'),
            raw={'username': name, 'verified': user.get('is_verified'), 'private': user.get('is_private'),
                 'followers': (user.get('edge_followed_by') or {}).get('count'), 'content_scope': 'user_profile'}))
    return items
