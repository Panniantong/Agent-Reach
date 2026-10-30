"""Read-only session discovery and explicit connection choices. Never logs a user in."""
import json
import urllib.request
from datetime import datetime
from urllib.parse import urlsplit

from agent_reach.utils.url import host_matches

from .result import BAD_INPUT, ReachError

# These describe public routes an agent can try, not authenticated Reach readiness.
# A successful sample depends on the tool, network exit, content and platform response.
_PUBLIC_ACCESS = {
    'web': 'Usa primero la búsqueda y lectura web propias del agente; Reach solo cubre lo que falte.',
    'github': 'Repos públicos, README, issues/PR y comentarios públicos se pueden leer primero por la web o la API pública.',
    'youtube': 'Búsqueda y descripción públicas se pueden leer primero; la herramienta nativa puede obtener a veces comentarios, subtítulos y marcas de tiempo.',
    'video': 'Vídeos públicos de TikTok e Instagram Reels: descripción, autor y estadísticas sin sesión; Instagram a veces exige iniciar sesión y entonces no se puede.',
    'bilibili': 'Búsqueda, descripción y estadísticas públicas se pueden leer primero; algunas interfaces públicas dan comentarios y respuestas.',
    'xiaoyuzhou': 'La transcripción de pódcasts necesita una clave de Groq; instalar no requiere iniciar sesión.',
    'v2ex': 'El cuerpo de los temas públicos y parte de las respuestas se pueden leer primero; la integridad y la paginación hay que comprobarlas aparte.',
    'reddit': 'Búsqueda, cuerpo y parte de los comentarios públicos se pueden leer primero; algunos JSON públicos incluyen comentarios y parent_id.',
    'twitter': 'Se pueden intentar resúmenes de búsqueda públicos y el texto de algunas publicaciones; los embebidos públicos no incluyen respuestas.',
    'xiaohongshu': 'La página pública de descubrimiento puede dar ID de notas y autores; eso no implica poder leer el cuerpo ni los comentarios.',
    'instagram': 'Se pueden intentar búsquedas públicas o datos del perfil; el HTML puede ser solo la carcasa de la app y los textos y comentarios no están verificados.',
    'facebook': 'Se pueden intentar resúmenes de búsqueda públicos; el cuerpo y los comentarios dependen de la página y de la ruta de acceso.',
    'linkedin': 'Se pueden buscar empleos públicos y leer su detalle; hay muestras sin sesión del 2026-10-21, pero no se garantiza poder leer todos.',
    'boss': 'Se pueden intentar el índice y las páginas públicas de empleos; no se ha probado el acceso anónimo en detalle.',
    'xueqiu': 'Se pueden intentar cotizaciones públicas y búsqueda por nombre; el contenido de la comunidad depende de la ruta elegida.',
}

_CAPABILITY_LIMITS = {
    'video': ['Solo publicaciones públicas; no hay búsqueda ni comentarios. Instagram puede responder "login required" y este canal no inicia sesión.'],
    'youtube': ['read devuelve metadatos y descripción; no hay una acción de comentarios.',
                'Los subtítulos dependen de las pistas disponibles; transcribir requiere un servicio y cuota configurados, y la sesión no garantiza subtítulos.'],
    'bilibili': ['read devuelve metadatos y descripción; no hay una acción de comentarios.',
                 'subtitle lee los subtítulos existentes de la primera parte; puede requerir sesión y no cubre vídeos de varias partes.'],
    'reddit': ['read solo garantiza las publicaciones y comentarios que devuelve; no garantiza el árbol completo ni permite comentar.'],
    'twitter': ['thread solo cubre las respuestas devueltas; no garantiza el hilo completo ni permite publicar.'],
    'xiaohongshu': ['Solo informa del cuerpo, los comentarios y las respuestas realmente cargados; no promete una exportación completa.'],
    'instagram': ['search busca usuarios; no hay read de publicaciones sueltas ni acción de comentarios.'],
    'facebook': ['Solo declara search/profile; no promete leer publicaciones sueltas ni exportar comentarios.'],
    'linkedin': ['Solo declara búsqueda de empleos y lectura de ofertas; no promete contactos ni publicaciones.'],
    'boss': ['Solo declara búsqueda de empleos y lectura de ofertas; la sesión no garantiza que la plataforma permita siempre el acceso.'],
    'v2ex': ['Si las respuestas están completas hay que comprobarlo con la paginación y el número devuelto.'],
}


# Public web options and authenticated Reach actions; detailed limits stay in capability_summary.
_QUICK_ACCESS = {
    'xiaoyuzhou': ('🔑 Transcribir necesita clave', '—'),
    'github': ('✅ Buscar proyectos, leer documentación, discusiones y comentarios', '—'),
    'youtube': ('✅ Buscar vídeos y Shorts, leer descripción y subtítulos', '—'),
    'video': ('✅ Leer TikTok y Reels, subtítulos y transcripción (con clave)', '—'),
    'bilibili': ('✅ Buscar vídeos, leer descripción', '❌ Leer subtítulos'),
    'v2ex': ('✅ Leer temas y respuestas', '—'),
    'web': ('✅ Buscar información, leer páginas', '—'),
    'reddit': ('✅ Buscar publicaciones, leer cuerpo y comentarios', '—'),
    'twitter': ('✅ Resúmenes de búsqueda, intentar leer publicaciones', '❌ Buscar tuits, ver actividad y respuestas'),
    'xiaohongshu': ('✅ Resúmenes de búsqueda, encontrar enlaces', '❌ Buscar en el sitio, leer cuerpo y comentarios'),
    'instagram': ('✅ Buscar resúmenes', '❌ Buscar usuarios, ver perfiles y publicaciones'),
    'facebook': ('✅ Resúmenes de búsqueda', '❌ Buscar en el sitio, ver perfiles'),
    'linkedin': ('✅ Encontrar empleos, leer ofertas públicas', '❌ Buscar dentro del sitio'),
    'boss': ('✅ Buscar títulos, encontrar enlaces', '❌ Buscar en el sitio, leer detalle'),
    'xueqiu': ('✅ Buscar acciones, ver cotizaciones', '❌ Ver publicaciones y acciones populares'),
}

_DISPLAY_NAMES = {
    'xiaoyuzhou': 'Xiaoyuzhou',
    'github': 'GitHub', 'youtube': 'YouTube', 'video': 'TikTok / Reels', 'bilibili': 'Bilibili', 'v2ex': 'V2EX',
    'web': 'Web', 'reddit': 'Reddit', 'twitter': 'X / Twitter', 'facebook': 'Facebook',
    'instagram': 'Instagram', 'xiaohongshu': 'Xiaohongshu', 'linkedin': 'LinkedIn',
    'boss': 'BOSS Zhipin', 'xueqiu': 'Xueqiu',
}

_STATUS_LABELS = {
    'not_added': 'no añadido, se puede añadir', 'needs_setup': 'pendiente de configurar', 'unverified': 'añadido, sin probar',
    'ready': 'probado y funcionando', 'search_ready': 'solo la búsqueda probada',
    'needs_login': 'la acción probada requiere sesión', 'cooldown': 'en pausa',
    'needs_user_action': 'esperando verificación manual', 'broken': 'la ruta actual falla',
}


def _local_greeting():
    """Use the installing computer's clock and timezone, without a network lookup."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return '¡Buenos días! ¿Qué quieres buscar? ☀️'
    if 12 <= hour < 20:
        return '¡Buenas tardes! ¿Qué quieres buscar?'
    return '¡Buenas noches! ¿Qué quieres buscar? 🌙'

def _upgrade_lines(result):
    """Only for users coming from 1.5: what was kept, what changed, what is left to do."""
    migration = result.get('migration')
    if not migration:
        return []
    lines = ['**Esta es una actualización desde la versión antigua (1.5):**', '',
             '- Tus claves y ajustes se han conservado.',
             '- Las suscripciones RSS y la búsqueda Exa ya no van aparte: para buscar y leer páginas se usa "Web".',
             '- Las plataformas que piden sesión, como Twitter o Xiaohongshu, usan ahora el navegador propio de Agent Reach; la primera vez intenta reutilizar la sesión de tu Chrome.',
             '- Las herramientas de terminal que instalaste aparte (como twitter-cli o bili) se han dejado tal cual.']
    suggested = [_DISPLAY_NAMES.get(n, n) for n in migration.get('suggested_channels') or []]
    if suggested:
        lines.append('- Antes usabas ' + ', '.join(suggested) + '; si quieres seguir, dime "añade XX".')
    old = result.get('old_copies') or {}
    if old.get('removed'):
        lines.append('- La versión antigua se ha borrado y ya no chocará con la nueva.')
    for item in old.get('failed') or []:
        from .legacy import manual_command
        lines.append(f"- No se pudo borrar la versión antigua; ejecuta: `{manual_command(item)}`")
    return lines + ['']



def installation_report(result):
    """Render one short receipt; keep detailed evidence in the structured summary."""
    def cell(value):
        return str(value).replace('|', r'\|').replace('\n', ' ')

    entries = result['capability_summary']['channels']
    installs = {row['channel']: row for row in result['default_channels']}
    installed = sum(bool(row['ok']) for row in installs.values())
    completed = all(row['ok'] for row in installs.values())
    lines = [
        _local_greeting(), '',
        f"**Agent Reach {result['version']} {'instalado' if completed else 'a falta de un paso para terminar la instalación'}.** "
        f'Funciones por defecto: {installed}/{len(installs)} listas.', '',
        *_upgrade_lines(result),
        '✅ sin sesión; ❌ con sesión; 🔑 necesita clave; — no necesita sesión extra.', '',
        '| Plataforma | Qué se puede consultar sin sesión | Qué necesita sesión |', '|---|---|---|',
    ]
    for entry in sorted(entries, key=lambda item: item['level'] != 'default'):
        name = entry['channel']
        label = _DISPLAY_NAMES.get(name, name)
        item = installs.get(name)
        if entry['level'] == 'default':
            if item and not item['ok']:
                label += ' (falló la instalación: ' + item.get('error', {}).get('code', 'UNKNOWN') + ')'
            elif not item:
                label += ' (quitado por el usuario)'
        elif entry['reach_status'] in {'needs_setup', 'needs_login', 'cooldown', 'needs_user_action', 'broken'}:
            label += ' (' + _STATUS_LABELS[entry['reach_status']] + ')'
        public, login = _QUICK_ACCESS.get(name, (entry['public_access'], '—'))
        lines.append('| ' + ' | '.join(cell(value) for value in (label, public, login)) + ' |')
    verified = [entry for entry in entries if entry['verified_actions']]
    if verified:
        names = '; '.join(_DISPLAY_NAMES.get(entry['channel'], entry['channel']) + ': ' +
                          '/'.join(entry['verified_actions']) for entry in verified)
        lines += ['', 'Probado y funcionando: ' + names + '. El resto aún no se ha probado uno a uno.']
    else:
        lines += ['', 'Aún no se ha probado cada plataforma con conexión.']
    lines += ['Resúmenes, títulos y enlaces se buscan primero en el buscador; los comentarios son los que se han leído y los subtítulos dependen del vídeo.', '',
              '**Dime qué quieres consultar.** Primero intentará reutilizar las sesiones existentes; solo si de verdad hace falta que inicies sesión, abrirá una ventana.']
    return '\n'.join(lines) + '\n'



def capability_summary(channels, statuses):
    """Describe public options, declared actions and local evidence without any I/O.

    Management supplies status records so this summary cannot initiate discovery,
    installation, login or a live request. Actions always come from the registry.
    """
    by_name = {entry['channel']: entry for entry in statuses}
    entries = []
    for ch in channels:
        current = by_name.get(ch.name, {})
        names = [action.name for action in ch.actions]
        can_login = bool(ch.login_url or ch.login_argv)
        auth_actions = {'bilibili': ['subtitle'], 'xueqiu': ['hot_posts', 'hot_stocks']}.get(
            ch.name, names if can_login else [])
        entries.append({
            'channel': ch.name,
            'level': ch.level,
            'reach_status': current.get('status', 'unverified'),
            'verified_actions': current.get('verified_actions', []),
            'actions': [{'action': action.name, 'detail': action.help} for action in ch.actions],
            'public_access': _PUBLIC_ACCESS.get(ch.name, 'Prueba primero la búsqueda y lectura públicas del agente.'),
            'authentication': {
                'when': 'only_if_required',
                'may_enable_actions': [name for name in auth_actions if name in names],
                'note': 'Si la ruta elegida para lo que falta exige autenticación, reutiliza primero una sesión autorizada y después pide al usuario que inicie sesión; tras iniciarla hay que volver a probar la acción.',
            },
            'limits': _CAPABILITY_LIMITS.get(ch.name, []),
        })
    message = ['Usa primero la búsqueda y lectura públicas del agente; Reach añade capacidades cuando hacen falta y la instalación no exige iniciar sesión en cada plataforma.']
    for entry in entries:
        actions = '/'.join(action['action'] for action in entry['actions'])
        status_label = _STATUS_LABELS.get(entry['reach_status'], entry['reach_status'])
        limits = ' '.join(entry['limits'])
        message.append(f"{entry['channel']}: {entry['public_access']} Reach {actions} ({status_label}). {limits}")
    return {
        'policy': 'public_first; login_only_for_remaining_task_when_required',
        'evidence_note': 'Las rutas públicas se describen a partir de muestras y condiciones de acceso; no sustituyen a una prueba de Reach en este equipo. Un fallo de red, un 403, un tiempo de espera o un captcha no demuestran por sí solos que haga falta iniciar sesión.',
        'channels': entries,
        'message': '\n'.join(message),
    }


def cdp_url():
    value = 'http://127.0.0.1:9222'
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
    from . import browser, session_reuse
    session_reuse.prepare("boss")
    if not cdp_status()['boss_tab_present']:
        browser.open_url('https://www.zhipin.com/web/geek/jobs')
    browser.touch()
    return browser.CDP_URL
