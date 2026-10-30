---
name: agent-reach
description: >
  Acceso de solo lectura a contenido de plataformas: buscar, leer publicaciones, ver comentarios, obtener subtítulos, cotizaciones y empleos.
  Úsalo cuando el usuario mencione o pegue un enlace de YouTube (vídeos, Shorts, subtítulos, transcripciones), TikTok, Instagram Reels,
  LinkedIn (empleos), Instagram, Facebook, Reddit, Twitter/X, GitHub, Bilibili, Xiaohongshu, V2EX,
  Xueqiu/cotizaciones, Boss Zhipin o pódcasts de Xiaoyuzhou; o diga "busca / mira / lee este enlace" y tu
  búsqueda o lectura web propia no esté disponible, falle o no obtenga el contenido;
  o quiera instalar, añadir/quitar una plataforma, iniciar/cerrar sesión, ver el estado, actualizar o desinstalar Agent Reach.
  No hace: publicar, comentar, dar "me gusta", enviar mensajes ni ninguna escritura; nunca inicia sesión por el usuario ni pide contraseñas.
  Para contenido público prefiere tus propias herramientas; Reach cubre los huecos.
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
  version: "{{VERSION}}"
---

# Agent Reach

Un comando para todas las plataformas: `agent-reach`. Solo lectura; por defecto imprime un objeto JSON.

Antes de actuar, di "uso la skill agent-reach (canal X)". Una vez invocada, estas reglas se aplican durante toda la sesión. Responde al usuario en español.

## Elegir la ruta

- Para contenido público, usa primero tus propias herramientas de búsqueda y lectura (opcionalmente `site:dominio`). Comprueba por separado el cuerpo del texto, los comentarios y los subtítulos; si bastan, responde directamente sin añadir canales ni iniciar sesión.
- Usa Reach cuando tus herramientas no estén disponibles, al resultado le falte lo que el usuario necesita o el usuario quiera una acción que declara un canal. ¿Dudas de acciones y parámetros? Ejecuta `agent-reach channels`.
- Un canal añadido (uno por defecto o uno añadido con `add`) envía search/read directamente a la herramienta de su sitio. Para canales aún no añadidos, search/read prueban primero el acceso web público anónimo; los resultados lo indican con `backend: public-web`. `--backend public-web` limita a la web pública; `--backend <backend>` elige una herramienta del sitio.
- El nombre de una plataforma o un enlace solo identifica la fuente; nunca provoca por sí solo una instalación ni un inicio de sesión.
- Fragmentos, páginas vacías, recuentos de comentarios y listas de pistas de subtítulos no son cuerpo, comentarios ni subtítulos; di qué tienes. Si el usuario no quiere iniciar sesión, entrega igualmente los resultados públicos ya obtenidos.

```bash
agent-reach channels                      # acciones y parámetros de cada canal
agent-reach <canal> <acción> [args]       # p. ej. agent-reach youtube search "recetas tiramisú" --limit 5
agent-reach read <url>                    # elige el canal según la URL
```

## Resultados y errores

- `ok: true` → contenido en `items`; cada uno tiene `title / url / author / published_at / text` y los datos originales en `raw`.
- `ok: false` → actúa según `error.code` y sigue `error.hint`:

| error.code | Qué hacer |
|---|---|
| `NEED_SETUP` | Falta una dependencia o una clave. Ejecuta `agent-reach add <canal>` según la pista; si es una clave, la pone el usuario y luego `agent-reach configure <clave>` |
| `NEED_LOGIN` | Conserva los resultados que ya tengas y dile al usuario que hace falta iniciar sesión; `agent-reach login <canal>` abre el navegador y el usuario inicia sesión él mismo. Nunca inicies sesión por él ni pidas una contraseña |
| `UPSTREAM_BROKEN` | La plataforma no funciona temporalmente; `message` es lo que se informó. Dile al usuario qué plataforma no está disponible y más o menos por qué, por nombre de plataforma, sin nombrar herramientas; ejecuta `agent-reach update` una vez, con su permiso, solo si el mensaje apunta a una herramienta desactualizada; nunca reintentes en bucle |
| `TIMEOUT` | Revisa la etapa que falló y el estado del canal (`agent-reach doctor --text`); no reintentes ni reabras ventanas en bucle |
| `RATE_LIMITED` | La plataforma limitó las peticiones y Reach pausó el canal. Espera `retry_after_seconds`; no cambies de backend |
| `PLATFORM_BLOCKED` | La plataforma pide verificación (captcha o control de riesgo). Para; el usuario lo resuelve en la página oficial. No cambies de cuenta ni de backend |
| `BUSY` | El navegador estuvo lleno durante los 2 minutos de espera, o el usuario tiene una ventana de inicio de sesión abierta. Reintenta más tarde, o cuando el usuario diga que ya inició sesión; no cierres la ventana ni cambies de perfil |
| `NOT_FOUND` | El contenido no existe; revisa el enlace o el ID |
| `BAD_INPUT` | Argumentos incorrectos; ejecuta `agent-reach channels` para ver el uso |

Ante `PLATFORM_BLOCKED`, `RATE_LIMITED`, `NEED_LOGIN` o `BUSY`, detén este intento; no reintentes con otras cuentas, backends ni navegadores. Un fallo de red o un fallo en una máquina no significa "la plataforma exige iniciar sesión".

## Inicio de sesión y navegador propio

Todos los canales con navegador comparten un navegador propio (preferentemente CloakBrowser; si no, el Chrome instalado). Por defecto funciona sin ventana, se cierra tras 10 minutos sin uso y se vuelve a abrir en la siguiente llamada. Las llamadas pueden ir en paralelo, también desde subagentes: hasta 2 por plataforma y 4 en total a la vez, el resto espera en cola, y dos búsquedas en la misma plataforma empiezan con al menos 10 segundos de diferencia.

La primera vez que se usa un sitio, si el Chrome del usuario está conectado a la extensión de OpenCLI, la sesión de ese sitio se copia una vez al navegador propio y se reutiliza después; solo se copia ese sitio y el navegador de origen no se toca. Solo cuando la sesión ha caducado o no hay de dónde copiarla, el usuario ejecuta `agent-reach login <canal>` e inicia sesión él mismo. Recomienda usar una cuenta secundaria. Renovar, elegir origen y cerrar sesión están en [Sesiones](references/sesiones.md): léelo cuando el usuario quiera iniciar o cerrar sesión o cambiar de cuenta, o ante `NEED_LOGIN`.

## Notas por plataforma

- YouTube: los enlaces de Shorts (`youtube.com/shorts/…`) funcionan igual que los vídeos normales. `subtitle` descarga una sola pista: subtítulos hechos por personas en español (o en inglés); si no hay, los automáticos en el idioma original del vídeo. Mira `raw.lang`: si no es español, traduce tú el texto al responder; no pidas otra pista traducida, porque YouTube limita mucho esas peticiones. Para preferir otro idioma usa `--lang`. Si el vídeo no tiene subtítulos, `transcribe` convierte el audio en texto (necesita una clave de Groq u OpenAI).
- TikTok e Instagram Reels: usa el canal `video` (`agent-reach video read|subtitle|transcribe|frames <enlace>`, o `agent-reach read <enlace>`). Va por yt-dlp, sin navegador ni sesión, así que solo sirve para publicaciones públicas. Para saber qué se dice en el vídeo, prueba `subtitle` y, si no hay, `transcribe`. Si Instagram responde "login required" o un límite, díselo al usuario: este canal no inicia sesión y el canal `instagram` no lee reels sueltos.
- Para entender lo que se ve en un vídeo de TikTok o un reel: `transcribe` devuelve cada frase con su momento (`[m:ss] texto`). Elige tú los momentos en que la imagen aclara lo que se dice (algo que señala o enseña, un texto o gráfico en pantalla, un producto, un cambio de escena, el primer plano del vídeo) y pídelos con `agent-reach video frames <enlace> --at "0:03,0:12,0:27"` (hasta 12). Cada resultado trae en `text` la ruta de un JPEG: ábrelo con tu herramienta de leer archivos para verlo y combina lo que ves con la transcripción. Sin transcripción (vídeo sin voz o sin clave de Whisper), `frames` sin `--at` saca 6 fotogramas repartidos por el vídeo. Las imágenes se borran solas al día siguiente.
- Fuera de `video frames`, Reach obtiene texto (título, descripción, subtítulos, transcripción), no imágenes: nunca afirmes haber visto lo que aparece en un vídeo o una imagen que no hayas abierto.
- Al leer Xiaohongshu solo se obtienen descripciones de texto; nunca afirmes entender las imágenes o el vídeo.
- Cuando un resultado de búsqueda de Boss Zhipin tenga `salary_encoded=true`, nunca adivines las cifras del salario; lee el enlace del empleo para ver el salario legible en el detalle.
- Qué ofrece cada plataforma públicamente y qué añade Reach está en [Alcance](references/capacidades.md): léelo cuando el usuario pregunte "qué puede obtener / está completo" o tengas que valorar si un resultado está completo.

## Canales

{{CHANNEL_TABLE}}

Los canales `default` se instalan por defecto y se pueden quitar; las actualizaciones nunca vuelven a añadir uno quitado. La columna `login` es la forma de autenticarse, no un requisito para el contenido público.

## Después de instalar

Tras `agent-reach setup`, muestra `result.installation_report.markdown` al usuario tal cual: sin añadir, quitar ni reordenar, sin saludos ni tablas extra. Lo genera el programa.

## Cuando el usuario quiere gestionar Agent Reach

| El usuario dice | Tú ejecutas |
|---|---|
| Añadir una plataforma | `agent-reach add <canal>`; las dependencias se instalan solas. Dile al usuario solo lo que debe hacer él (iniciar sesión o dar una clave) |
| Quitar una plataforma | `agent-reach remove <canal>` |
| Iniciar sesión / la sesión caducó | `agent-reach login <canal>`; el usuario inicia sesión él mismo en la ventana que se abre |
| Cerrar sesión | `agent-reach logout <canal>` |
| Estado / qué funciona | `agent-reach doctor --text`; para una prueba real `agent-reach check <canal> --text` |
| Actualizar | `agent-reach update` |
| Desinstalar | muestra primero `agent-reach uninstall --dry-run` y después `agent-reach uninstall` cuando confirme |
| Que otra IA también lo use | `agent-reach skill link <carpeta de skills de esa IA>`; `agent-reach skill` muestra dónde está ahora |

Resolución de problemas, mantenimiento del navegador y desinstalación están en [Mantenimiento](references/mantenimiento.md): léelo cuando falle una actualización, el navegador no arranque o el usuario quiera desinstalar.

## Cuando hay una versión nueva

Cualquier resultado con `meta.update` indica que hay una versión más reciente. Menciónalo una vez por conversación, en lenguaje sencillo:

1. Agent Reach tiene una versión nueva (`meta.update.latest`).
2. Qué cambia: de 1 a 3 puntos breves de `meta.update.notes`.
3. Pregunta si quiere actualizar; ejecuta `agent-reach update` solo si el usuario está de acuerdo.

## Líneas rojas

- Solo lectura. Nunca publiques, comentes, des "me gusta" ni envíes mensajes.
- Nunca inicies sesión por el usuario; nunca pidas ni muestres contraseñas, cookies u otras credenciales.
- Las consultas normales nunca cambian dependencias ni actualizan automáticamente.
