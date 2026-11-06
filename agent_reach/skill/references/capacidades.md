# Alcance

Léelo cuando el usuario pregunte qué se puede obtener o si un resultado está completo. La tabla recoge capacidades declaradas, no garantiza que todas las redes, cuentas y contenidos se hayan probado.

## Tres niveles

- **Público, se puede intentar**: las herramientas web del agente, las herramientas nativas o las interfaces públicas pueden bastar para la tarea; no hace falta instalar el navegador ni iniciar sesión. Responde según lo que realmente obtengas.
- **Lo que añade Reach**: las acciones que declara esta versión, ver `agent-reach channels`. Si hace falta configurar algo, reutiliza primero la sesión guardada en el navegador propio; el usuario inicia sesión solo cuando la ruta elegida lo exige de verdad.
- **Verificado en este equipo**: solo las acciones concretas que han pasado una prueba reciente aquí; instalar, guardar una sesión o tener red no equivale a haberlo probado.

## Canales de esta versión

| Canal | Ruta pública que se puede intentar | Lo que añade Reach y sus límites |
|---|---|---|
| GitHub | Repos públicos, README, issues y PR | Buscar repos, leer repos/issues/PR y los comentarios devueltos; los permisos privados se valoran aparte |
| YouTube | Búsqueda, título y descripción; las herramientas nativas pueden obtener algunos comentarios y subtítulos | search/read/subtitle/transcribe, también para Shorts; no hay una acción de comentarios; una lista de pistas no es el texto de los subtítulos; sin subtítulos, la transcripción depende de una clave |
| TikTok / Reels (`video`) | Descripción, autor y estadísticas de publicaciones públicas | read/subtitle/transcribe por yt-dlp, sin navegador ni sesión; transcribe con marcas de tiempo y frames (fotogramas JPEG en los momentos que elijas, o 6 repartidos); sin búsqueda ni comentarios; Instagram puede exigir sesión y entonces no se puede leer |
| Bilibili | Búsqueda y descripción; algunas interfaces públicas devuelven comentarios con IDs de respuesta | search/read/hot/subtitle; no hay acción de comentarios; los subtítulos dependen del vídeo y de la ruta de acceso |
| Reddit | Búsqueda, cuerpo y algunos comentarios; algunos JSON públicos incluyen IDs de respuesta | search/read/subreddit con navegador; la sesión depende de la ruta elegida; no garantiza el árbol completo de comentarios; no comenta |
| X/Twitter | Publicaciones públicas que aparecen en búsquedas; algunos embebidos oficiales dan el texto completo | search/profile/tweets/thread; poder leer una publicación no implica poder leer sus respuestas; no garantiza el hilo completo |
| Xiaohongshu | Listas o índices públicos pueden dar ID, autor y título; no rellenes campos vacíos inventando | search/read/comments; texto, comentarios principales y respuestas cargadas; no garantiza todos los comentarios ni entiende imágenes o vídeo |
| Instagram | Algunos índices e información superficial de perfiles; la página vacía de la app no es una publicación | search busca usuarios, profile perfil, posts descripciones de publicaciones de un usuario; no hay acción de comentarios ni de reels sueltos; no entiende imágenes ni vídeo |
| Facebook | Algunos índices o resúmenes HTML, que pueden venir recortados | search/profile; no hay acción de detalle ni de comentarios; un resumen de búsqueda no es el texto completo |
| LinkedIn | Buscar empleos públicos y leer ofertas públicas | jobs/read prueban primero la web pública; solo con `--backend opencli` van dentro del sitio; no garantiza poder leer todas las ofertas |
| BOSS | El índice de búsqueda puede tener resúmenes de empleos | search/read de listas de empleos y ofertas; no adivines salarios codificados |
| V2EX | Temas, cuerpo y respuestas públicas | hot/node/read/user; el alcance es lo que devuelve la respuesta, no garantiza respuestas ocultas o que falten |
| Xueqiu | Algunas cotizaciones e información de índices públicos | quote/search/hot_posts/hot_stocks; cotizaciones y comunidad se prueban por separado |
| Web | Búsqueda y lectura propias del agente | search/read de Reach como respaldo anónimo; fragmentos, páginas vacías y páginas de verificación no son el texto completo |
| Xiaoyuzhou | Título y descripción de la página del episodio | transcribe convierte el episodio en texto; el usuario debe dar una clave de Groq (`agent-reach configure groq-key`) |

Después de iniciar sesión, di "se pueden activar o intentar las acciones de navegador anteriores", no "con sesión se obtienen todos los comentarios". Si el usuario no quiere iniciar sesión, entrega lo público que ya tengas.
