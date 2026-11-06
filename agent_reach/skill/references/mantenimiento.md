# Mantenimiento

Léelo cuando falle una actualización, el navegador no arranque, un canal dé error o el usuario quiera desinstalar.

- Actualizar: `agent-reach update` actualiza Agent Reach, las herramientas de los canales añadidos y la skill; `agent-reach update --check` solo comprueba si hay versión nueva. Ejecútalo solo con el permiso del usuario. En este fork instalado en modo editable, `update` no reemplaza el programa: para traer cambios del proyecto original hay que fusionarlos en el repositorio del fork.
- Estado: `agent-reach doctor --text` lee el estado local sin conectarse; `agent-reach check <canal> --text` hace una prueba real (`--search` solo prueba búsqueda/empleos). Instalar bien no equivale a haberlo probado.
- Navegador: `agent-reach browser status` muestra el estado, `browser setup` prepara el navegador y la extensión, y `browser stop` lo cierra; si la descarga de CloakBrowser falló, cuando la red funcione usa `browser setup --retry-cloak`.
- Distingue en qué etapa falla: descarga de dependencias, conexión del navegador, sesión, carga de la página y límites de la plataforma son cosas distintas; un tiempo de espera de red no es una sesión caducada.
- Errores de herramientas externas: anota el error y la versión y, con permiso del usuario, ejecuta `agent-reach update` una vez; no modifiques los archivos instalados de esas herramientas ni reintentes en bucle.
- Ante `PLATFORM_BLOCKED`, `RATE_LIMITED`, `NEED_LOGIN` o `BUSY`, detén este intento y espera a que el usuario lo resuelva; no abras ventanas una y otra vez.
- Claves y proxy: `agent-reach configure groq-key | openai-key | proxy | github-token`; los valores los introduce el propio usuario en su terminal.
- Desinstalar: muestra primero `agent-reach uninstall --dry-run` y, cuando el usuario confirme, `agent-reach uninstall`. Solo borra lo que instaló Reach; los demás archivos y navegadores del usuario se conservan.
