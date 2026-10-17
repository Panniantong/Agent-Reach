"""Read Facebook search cards in a Cloak-owned browser session."""
from urllib.parse import parse_qs, urlencode, urlsplit

from agent_reach.runtime.result import ReachError, make_item
from agent_reach.utils.url import domain_matches


def normalize(rows, limit):
    items, seen = [], set()
    excluded = ('search', 'login', 'checkpoint', 'help', 'privacy', 'policies', 'settings',
                'notifications', 'messages', 'friends', 'marketplace', 'gaming', 'bookmarks')
    for row in rows:
        u = urlsplit(row.get('url') or '')
        title = ' '.join(str(row.get('title') or '').split())
        if u.scheme != 'https' or not domain_matches(u.hostname or '', 'facebook.com'):
            continue
        if u.hostname in {'l.facebook.com', 'lm.facebook.com'} or u.path == '/' or u.path.strip('/').split('/')[0] in excluded:
            continue
        if not title or title.isdigit():
            continue
        keep = {'id', 'story_fbid', 'story_id', 'fbid', 'v'}
        query = urlencode({k: v[0] for k, v in parse_qs(u.query).items() if k in keep})
        url = f'{u.scheme}://{u.netloc}{u.path}' + ('?' + query if query else '')
        if url in seen:
            continue
        seen.add(url)
        items.append(make_item(title=title[:250], url=url, raw={'content_scope': 'search_card'}))
        if len(items) == limit:
            break
    return items


def search(page, query, limit):
    from playwright.sync_api import TimeoutError
    response = page.goto('https://www.facebook.com/search/top?' + urlencode({'q': query}),
                         wait_until='domcontentloaded', timeout=25000)
    if response and response.status == 429:
        raise ReachError('RATE_LIMITED', 'Facebook rate limit')
    selector = '[role="feed"] a[href], [role="main"] a[href]'
    try:
        page.wait_for_selector(selector, timeout=10000)
    except TimeoutError:
        pass
    path = urlsplit(page.url).path
    if path.startswith('/checkpoint'):
        raise ReachError('PLATFORM_BLOCKED', 'Facebook account verification required')
    if path.startswith('/login') or page.locator('input[type="password"]:visible').count():
        raise ReachError('NEED_LOGIN', 'Facebook login required')
    rows = page.locator(selector).evaluate_all('els => els.map(e => ({title:e.innerText, url:e.href}))')
    items = normalize(rows, limit)
    if not items:
        raise ReachError('UPSTREAM_BROKEN', 'Facebook search cards did not load')
    return items
