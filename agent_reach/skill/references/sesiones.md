# Sesiones y navegador propio

Léelo cuando el usuario quiera iniciar o cerrar sesión, cambiar de cuenta, o cuando un resultado devuelva `NEED_LOGIN`.

## Navegador propio

- Todos los canales con navegador comparten una configuración de navegador propia, separada del Chrome diario del usuario; el programa no cierra ni modifica el navegador diario.
- Usa preferentemente CloakBrowser (un Chromium modificado por CloakHQ, sin firma digital); si su descarga o instalación falla, usa el Chrome instalado y recuerda esa alternativa para no volver a descargar cada vez. Cuando la red funcione, se puede reintentar con `agent-reach browser setup --retry-cloak`.
- `agent-reach add <canal>` prepara automáticamente Node, OpenCLI, el navegador y la extensión, en las versiones probadas para esta versión. En Windows, con Chrome como alternativa, puede que el usuario tenga que pulsar una vez "Añadir a Chrome".
- Por defecto funciona sin ventana. Solo `agent-reach login <canal>` muestra una ventana; mientras está abierta, las consultas usan esa ventana y no la cierran. Mientras el usuario inicia sesión, espera a que diga que ha terminado antes de consultar. Al cerrar la ventana, las consultas vuelven a ir sin ventana.
- Se cierra solo tras 10 minutos sin uso y se reabre en la siguiente llamada; el uso real de páginas y las llamadas a Reach reinician el contador. Durante el inicio de sesión se guarda periódicamente, el usuario no tiene que cerrar la ventana.
- Admite paralelo: hasta 2 a la vez por plataforma y 4 en total; el resto espera en cola hasta 2 minutos y, si no entra, devuelve `BUSY`. Dos búsquedas en la misma plataforma van separadas al menos 10 segundos. Abrir una ventana de inicio de sesión, cerrar sesión o reinstalar el navegador espera a que terminen las consultas en curso.
- `agent-reach browser status` muestra el estado, `browser setup` prepara el navegador y la extensión, y `browser stop` cierra el navegador gestionado por el programa.

## Reutilizar sesiones existentes

1. La primera vez que se usa un sitio, si el Chrome del usuario está conectado a la extensión de OpenCLI, el programa copia una vez la sesión de ese sitio (solo sus cookies) al navegador propio. No copia la carpeta del navegador, otros sitios ni el gestor de contraseñas, y no modifica el navegador de origen.
2. Tras copiarla, reutiliza siempre la sesión guardada; no la vuelve a copiar por tiempo. Que existan cookies no significa que la sesión sea válida: lo decide el resultado real.
3. Si el Chrome del usuario no está conectado a la extensión, no se puede prometer la reutilización automática ni concluir que el usuario no ha iniciado sesión; en ese caso se usa la sesión que Reach ya tenga guardada.
4. Si varios navegadores del equipo tienen sesión en ese sitio: `agent-reach browser profiles` los lista y `agent-reach browser use <ID>` fija uno; no cambies al azar.
5. `agent-reach login <canal> --import-existing` vuelve a copiar la sesión de ese sitio sin abrir ventana.
6. Si el usuario inició sesión él mismo en la ventana propia, o ejecutó `logout` / `remove`, ya no se copia automáticamente, para no revivir una sesión cerrada.

## Cuando el usuario debe iniciar sesión

- Pide al usuario que inicie sesión solo cuando un resultado devuelva de verdad `NEED_LOGIN` y la tarea pendiente necesite esa ruta. Que la página tenga un botón de inicio de sesión no cuenta.
- `agent-reach login <canal>` abre el navegador propio en la página de inicio de sesión del sitio y el usuario lo completa él mismo. Tú no inicias sesión, no pides contraseñas y no muestras cookies. Recomienda una cuenta secundaria.
- El navegador propio está en inglés a propósito: las herramientas que lo controlan buscan textos en inglés. Recomienda que la cuenta usada también tenga la interfaz en inglés (en LinkedIn, con la cuenta en español falla la búsqueda). Antes de escribir nada, el usuario debe comprobar que la barra de direcciones muestra el dominio oficial.
- Si el resultado trae pasos en `next`, síguelos; algunos canales con herramienta propia (como Xueqiu) necesitan `agent-reach login <canal> --sync` después de iniciar sesión.
- Cuando el usuario termine, vuelve a ejecutar la acción original para comprobarlo.

## Diferencias por plataforma

- La búsqueda de Boss Zhipin usa OpenCLI y comparte el navegador propio. Si el detalle de un empleo pide iniciar sesión por un falso positivo, no hagas que el usuario inicie sesión una y otra vez.
- Bilibili solo pasa la sesión a su herramienta oficial al leer subtítulos; las búsquedas normales no preparan el navegador.
- Las acciones de comunidad de Xueqiu requieren sesión; caduca en pocas horas y luego hay que repetir el inicio de sesión.

## Cerrar sesión y quitar canales

- `agent-reach logout <canal>`: borra la sesión de ese sitio en el navegador propio y el estado del canal; los demás sitios se conservan.
- `agent-reach remove <canal>`: quita el canal y borra la sesión y los datos de ese sitio; los demás sitios se conservan. Si la limpieza falla, el canal sigue registrado y se devuelve un error para reintentar.
- Después de cualquiera de los dos, la sesión de ese sitio ya no se copia automáticamente.
