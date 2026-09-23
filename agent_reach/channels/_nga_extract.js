(() => {
  // Read rendered NGA post elements only. Never access cookies or page internals.
  const here = new URL(document.URL);
  const tid = here.searchParams.get('tid');
  const page = Number(here.searchParams.get('page') || 1);
  const text = el => (el?.innerText ?? el?.textContent ?? '').trim();
  const httpURL = value => {
    if (!value) return null;
    try {
      const url = new URL(value, here);
      return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
    } catch { return null; }
  };
  const navigation = [...document.querySelectorAll('#m_pbtntop a, #m_pbtnbtm a')]
    .map(a => httpURL(a.getAttribute('href'))).filter(Boolean)
    .map(href => new URL(href))
    .filter(u => u.origin === here.origin && u.pathname === '/read.php'
      && u.searchParams.get('tid') === tid);
  const totalPages = Math.max(page, ...navigation.map(u => Number(u.searchParams.get('page') || 1)));
  const posts = [...document.querySelectorAll('[id^="postcontainer"]')]
    .filter(el => /^postcontainer\d+$/.test(el.id))
    .map(container => {
      const index = container.id.slice('postcontainer'.length);
      const content = document.getElementById('postcontent' + index);
      const author = document.getElementById('postauthor' + index);
      const info = document.getElementById('posterinfo' + index);
      const floorLink = info?.querySelector('a[href*="#pid"]');
      const anchor = container.querySelector('a[id^="pid"][id$="Anchor"]');
      const pid = anchor?.id.match(/^pid(\d+)Anchor$/)?.[1];
      const authorURL = httpURL(author?.getAttribute('href'));
      // NGA prepends a decorative name initial; it is not part of the nickname.
      const authorName = author ? [...author.childNodes]
        .filter(n => n.nodeType !== 1 || n.getAttribute('name') !== 'nameinit')
        .map(n => n.textContent).join('').trim() : '';
      const images = [...(content?.querySelectorAll('img') || [])]
        .filter(img => !img.className.includes('smile') && img.style.display !== 'none')
        .map(img => {
          const url = ['data-srcorg', 'data-srclazy', 'src']
            .map(attr => httpURL(img.getAttribute(attr))).find(Boolean);
          return url ? {url, alt: img.getAttribute('alt') || ''} : null;
        }).filter(Boolean);
      const links = [...(content?.querySelectorAll('a[href]') || [])]
        .map(a => ({text: text(a), url: httpURL(a.getAttribute('href'))}))
        .filter(a => a.url);
      return {
        pid: pid ?? null,
        floor: Number(text(floorLink).replace(/^#/, '')),
        author: authorName,
        author_uid: authorURL ? new URL(authorURL).searchParams.get('uid') : null,
        created_at: text(document.getElementById('postdate' + index)),
        text: text(content), images, links,
        url: httpURL(floorLink?.getAttribute('href')),
        edited: text(document.getElementById('alertc' + index)),
        content_present: Boolean(content)
      };
    });
  const title = text(document.getElementById('postsubject0'))
    || text(document.querySelector('#m_nav a[href*="read.php"]'))
    || document.title.replace(/\s*NGA玩家社区\s*$/, '').trim();
  return {url: here.href, tid, page, total_pages: totalPages, title, posts};
})()
