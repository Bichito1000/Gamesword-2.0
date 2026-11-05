# 🎮 GAMESWORD 2.0.0
**Todos tus juegos. Una sola experiencia.**

Centro gaming para Windows 10/11 con diseño futurista (negro, morado y azul neón): biblioteca unificada,
lanzadores, estadísticas reales, asistente de IA con voz, rendimiento, amigos con chat, descubrimiento de juegos,
bandeja del sistema, atajos globales y navegación con mando.

Python 3.10+ · PySide6 · SQLite · FastAPI (servidor de amigos)

---

## Contribuir y ejecutar los tests
```
git clone https://github.com/TU-USUARIO/gamesword.git
cd gamesword
python -m unittest discover -s tests -t .      # 59 pruebas, sin necesidad de PySide6
```
Los datos del usuario (`data/`, `logs/`, ajustes, claves, copias) están en `.gitignore` y no se suben nunca.
Si encuentras un fallo, adjunta el informe de *Ajustes → Crear informe de diagnóstico* (no incluye tus claves).

## Instalación (Windows)
1. Instala **Python 3.10 o superior** (python.org, marca *Add python.exe to PATH*).
2. Descomprime el proyecto y ejecuta **`INSTALAR_Y_ABRIR.bat`** (la primera vez descarga dependencias).
3. Después usa **`ABRIR_GAMESWORD.bat`**. Si falla algo: `logs/gamesword.log` o *Ajustes → Crear informe de diagnóstico*.

Scripts: `INICIAR_SERVIDOR.bat` · `CREAR_CERTIFICADO_HTTPS.bat` · `CREAR_EXE.bat` · `EJECUTAR_TESTS.bat`.

## Novedades de la 2.0.0 (Etapa 1)
| Área | Qué hay |
|---|---|
| **Colecciones** | Botón *🗂 Colecciones* y clic derecho en un juego; filtro por colección |
| **Perfil** | Pestaña *Perfil*: avatar, nivel, XP, insignias, desafíos de hoy y de la semana, favoritos e historial |
| **Logros** | 20 logros con XP, también por usar Gamesword (IA, sincronizar, colecciones, copias, personalizar…) |
| **Copias de seguridad** | *Ajustes → Copias de seguridad*; automática cada día; si la base se daña, se recupera sola de la última copia |
| **IA** | Botones *Sí / Cancelar* antes de cerrar o quitar juegos; memoria («recuerda que…»); comandos personalizados; diagnóstico del PC |
| **Personalización** | Modo compacto y colores propios (*Ajustes → Apariencia*) |

Cómo se calcula el nivel: 10 XP por hora jugada (incluye las horas importadas de Steam) + la XP de logros y desafíos.
Nivel 2 a los 100 XP, nivel 3 a los 300, nivel 4 a los 600…

Qué está pendiente de la lista completa del 2.0 (comunidad avanzada, rendimiento con historial/overlay, personalización
avanzada): ver `CHANGELOG.md`.

## Tu biblioteca COMPLETA (no solo lo instalado)
Pulsa **Biblioteca → Sincronizar bibliotecas** (también se hace al abrir Gamesword). Los juegos que posees pero no tienes
instalados salen **apagados con la etiqueta «NO INSTALADO»** y un botón **INSTALAR**; hay un filtro *Todos / Instalados / No instalados*.

Las plataformas no dejan leer tu catálogo sin que se lo permitas tú, así que cada una necesita un paso único:

| Plataforma | Qué hacer una vez | Qué obtienes |
|---|---|---|
| **Steam** | *Ajustes → Biblioteca*: pega tu clave de API (steamcommunity.com/dev/apikey). El SteamID se detecta solo. Perfil y «detalles de juego» en **Público**. | Todos tus juegos + tus horas |
| **Epic** | `.venv\Scripts\pip install legendary-gl` y, en una terminal, `legendary auth` (inicias sesión en la web oficial de Epic; Gamesword no ve tu contraseña) | Toda tu biblioteca de Epic |
| **Ubisoft, EA, Xbox, Battle.net, GOG** | Instala **GOG Galaxy 2.0**, conecta esas cuentas y ábrelo una vez | Sus juegos aparecen en Gamesword |

Sin estos pasos solo pueden detectarse los instalados: Ubisoft, EA, Xbox y Battle.net no tienen ninguna API pública para
listar tu catálogo. La lectura de GOG Galaxy usa su base de datos interna (no documentada) y se desactiva sola si cambia.

## Novedades de la 1.1
| Área | Qué hay |
|---|---|
| **Seguridad** | Claves (IA, Steam, RAWG, sesión) en el **Administrador de credenciales de Windows** (`keyring`); 30 tests automáticos; informe de diagnóstico sin claves; aviso si el servidor va por `http://` |
| **Juegos** | Detección añadida de **Xbox/Game Pass**, **Battle.net** y **Rockstar**; **importación de horas de Steam** (API oficial, sin duplicar); portadas alternativas con **RAWG** |
| **Sistema** | Icono en la **bandeja**, inicio con Windows y minimizado, **Ctrl+Alt+G** (mostrar/ocultar) y **Ctrl+Alt+V** (hablar con la IA), **mando Xbox**, **Discord Rich Presence**, iconos vectoriales y transición suave |
| **IA** | **Herramientas nativas** del modelo (abrir, horas, biblioteca, recomendar, estado del PC) con vuelta automática al modo texto, **respuesta en streaming**, reconocimiento de voz **local con Whisper** y palabra **«Oye Gamesword»** |
| **Rendimiento** | CPU/RAM/GPU(NVIDIA)/VRAM en vivo, programas que más memoria usan (cierre solo con tu confirmación) y plan de energía Alto rendimiento |
| **Social** | **Cuentas con contraseña** (PBKDF2, bloqueo anti-fuerza-bruta), **HTTPS**, **chat de grupo** e **invitaciones a jugar** |
| **Negocio** | **Actualizaciones** con comprobación SHA-256, **telemetría opcional** anónima, **licencias Plus/Pro** firmadas (Ed25519) |

## Uso rápido
Atajos: `Ctrl+1…9` cambia de sección. Con mando: D-pad/stick mueve, **A** acepta, **B** vuelve a Inicio, **LB/RB** cambian de
página, **X/Y** cambian de control, **Start** abre la IA (solo cuando Gamesword tiene el foco).

**Gamesword AI** funciona sin clave para: «Ábreme Fortnite», «Abre Discord y después Rocket League», «¿Qué juegos tengo?»,
«¿Cuántas horas he jugado esta semana?», «algo parecido a GTA V», «cooperativos de terror», «¿cómo va mi PC?».
Con una clave (OpenAI, OpenRouter, Groq u Ollama local) conversa libremente y puede ejecutar esas mismas acciones.

## Configuración opcional (todo en *Ajustes*)
- **Steam**: pega tu SteamID64 y una clave de steamcommunity.com/dev/apikey (perfil y detalles de juego en Público) → *Importar mis horas*.
- **RAWG**: clave gratuita en rawg.io/apidocs para portadas de juegos que no están en Steam.
- **Discord Rich Presence**: crea una aplicación en discord.com/developers, copia su *Application ID* y `pip install pypresence` (el instalador lo intenta).
- **Whisper local**: `.venv\Scripts\pip install -r requirements-whisper.txt`, elige *Local con Whisper* y activa la palabra de activación. Nada de audio sale de tu PC.
- **Micrófono**: lo instala el `.bat` si hay rueda de PyAudio para tu Python. Con el motor «Google» el audio se envía a Google.

## Servidor de amigos
1. `INICIAR_SERVIDOR.bat` (S = aceptar conexiones de tu red; N = solo este PC).
2. En Gamesword → **Amigos**: dirección del servidor, usuario y contraseña (mín. 8) → *Crear cuenta*.
3. Comparte tu código de amigo; los grupos se unen con código y tienen chat. *Invitar a jugar* avisa al amigo.

**HTTPS**: para Internet usa un dominio y Caddy/Nginx (certificado real), o `CREAR_CERTIFICADO_HTTPS.bat` para un
certificado autofirmado (desactiva *Verificar certificado* en Ajustes → Online). Sin HTTPS las contraseñas viajan sin cifrar:
úsalo solo en red de confianza. El servidor no incluye moderación ni límites avanzados: no lo abras al público sin más.

## Actualizaciones
Aloja tu instalador y un `update.json` por HTTPS (`python tools/make_manifest.py Gamesword-Setup-1.2.0.exe --version 1.2.0 --url https://…`).
Pon la URL del manifiesto en *Ajustes → Actualizaciones*. La versión instalada (.exe) descarga, verifica el SHA-256 y se actualiza sola;
en modo desarrollo solo abre la página de descarga. **Firma tu instalador**: sin certificado de firma de código, SmartScreen avisará.

## Licencias Plus / Pro
Por defecto **todo está desbloqueado** (`ENFORCE_LICENSES = False` en `core/licensing.py`). Cuando quieras cobrar:
1. `python tools/license_tool.py keygen` → pega la clave pública en `PUBLIC_KEY_HEX` (la privada `tools/private.key` NUNCA se distribuye).
2. `python tools/license_tool.py issue --tier plus --name "Ana" --days 365` → el cliente la pega en *Ajustes → Licencia*.
3. Ajusta `FEATURES` (qué función exige qué nivel) y pon `ENFORCE_LICENSES = True`.
Aviso honesto: una licencia verificada en el cliente frena el uso casual, no a quien edite el código.

## .exe e instalador
`CREAR_EXE.bat` (PyInstaller; define `GAMESWORD_PFX` y `GAMESWORD_PFX_PASS` para firmarlo) → abre `installer.iss` con Inno Setup 6 y compila.
Instalado, los datos van a `%LOCALAPPDATA%\Gamesword`.

## Estructura
```
main.py · config/settings.py · utils/ (paths, logger, helpers, qt_async)
core/        progress, backup, database, game_detector, library_sync, galaxy_import, epic_import, game_launcher, game_tracker, platform_manager, covers, steam_import, social,
             system_monitor, secrets_store, licensing, ed25519, updater, telemetry, diagnostics,
             autostart, hotkeys, gamepad, rich_presence, context, models
ai/          assistant, recommendations, catalog, voice
interface/   main_window y una vista por sección, theme, icons, widgets, dialogs
server/      app, store, make_cert (python -m server)        tools/  license_tool, make_manifest
tests/       python -m unittest discover -s tests -t .
```

## Límites conocidos
- **FPS en juego**: no se pueden medir sin inyectarse en el juego (los anti-trampas lo bloquean). Usa el overlay de Steam/NVIDIA/Afterburner.
- La GPU solo se mide en **NVIDIA** (`nvidia-smi`).
- Battle.net/Rockstar/Xbox se detectan por registro y carpetas estándar; instalaciones en rutas raras pueden requerir añadirse a mano.
- El catálogo de *Descubrir* es offline (~70 juegos); RAWG solo se usa para portadas.
- Servidor de amigos: pensado para grupos pequeños y redes de confianza.
