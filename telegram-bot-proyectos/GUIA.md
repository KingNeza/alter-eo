# Bot de Telegram para seguir tus proyectos — con GitHub Actions (gratis)

Este bot recibe lo que le mandas por Telegram, lo guarda en una hoja de Google Sheets
y te manda un resumen cada mañana con lo vencido y lo que vence pronto.

Corre **gratis en GitHub Actions**, sin tarjeta y sin servidor propio.

## Cómo funciona (importante entenderlo)

GitHub Actions no mantiene un programa encendido todo el día. En su lugar, **despierta
cada 5 minutos**, revisa si le mandaste mensajes nuevos, actualiza la hoja y te responde.
Un segundo trabajo corre **cada mañana a las 8:00 (CDMX)** y te manda el resumen.

Consecuencia: las respuestas **no son instantáneas**, pueden tardar hasta unos minutos.
Para un tablero de proyectos personales eso funciona bien. Si algún día quieres respuestas
al instante, se puede migrar a un host de pago (~$2/mes); avísame.

Vas a hacer, una sola vez:
1. Preparar el acceso a Google Sheets.
2. Subir esta carpeta a un repositorio de GitHub.
3. Cargar 3 "secrets" en GitHub.
4. Escribirle `/start` a tu bot.

---

## Paso 1 — Acceso a Google Sheets (service account)

El bot entra a tu hoja con una "cuenta de servicio": un usuario robot de Google al que
le das permiso solo sobre esa hoja.

1. Entra a <https://console.cloud.google.com/> con tu cuenta de Google.
2. Crea un proyecto nuevo (selector de proyectos arriba → **Nuevo proyecto**), nómbralo
   como quieras (p. ej. `bot-proyectos`).
3. Habilita dos APIs (búscalas en la barra de arriba y dale **Habilitar** a cada una):
   **Google Sheets API** y **Google Drive API**.
4. Ve a **APIs y servicios → Credenciales → Crear credenciales → Cuenta de servicio**.
   Nómbrala (p. ej. `bot-sheets`) y dale **Crear y continuar → Listo**.
5. Entra a esa cuenta de servicio → pestaña **Claves → Agregar clave → Crear clave nueva
   → JSON**. Se descarga un archivo `.json`. **Guárdalo bien**, es la llave.
6. Abre el `.json` y copia el `client_email` (algo como
   `bot-sheets@bot-proyectos.iam.gserviceaccount.com`).

## Paso 2 — Crea y comparte tu hoja

1. Crea una hoja nueva en <https://sheets.google.com>. No necesitas crear columnas: el bot
   arma las pestañas `Proyectos`, `_config` y `_chats` solo la primera vez.
2. Dale **Compartir** y agrega el `client_email` del paso anterior como **Editor**.
3. Copia el **ID de la hoja** de la URL, entre `/d/` y `/edit`. En
   `https://docs.google.com/spreadsheets/d/`**`1AbC...xyz`**`/edit` el ID es `1AbC...xyz`.

## Paso 3 — Sube la carpeta a GitHub

1. Crea una cuenta en <https://github.com> si no tienes.
2. Crea un repositorio nuevo (**New repository**). Puede ser **público** (recomendado: así
   los minutos de Actions son ilimitados) o privado. En el código **no hay** datos
   sensibles —el token y la llave van aparte, como secrets— así que público es seguro.
3. Sube esta carpeta al repo. La forma más fácil sin usar la terminal:
   en la página del repo vacío, **uploading an existing file** y arrastra todos los
   archivos, **incluyendo la carpeta `.github`** (trae los dos workflows).
   > Si GitHub no te deja arrastrar carpetas ocultas, sube primero los archivos sueltos y
   > luego crea los archivos `.github/workflows/poll.yml` y `.github/workflows/reminder.yml`
   > con **Add file → Create new file** pegando su contenido.

## Paso 4 — Carga los Secrets en GitHub  ← aquí van las variables

En tu repo: **Settings → Secrets and variables → Actions → New repository secret**.
Crea estos tres (pestaña *Secrets*, no *Variables*):

| Nombre del secret | Valor |
|---|---|
| `BOT_TOKEN` | El token de tu bot (`8784623506:AAE...jpk`). |
| `SPREADSHEET_ID` | El ID de la hoja del Paso 2. |
| `GOOGLE_CREDENTIALS` | El contenido **completo** del `.json`, tal cual (pégalo entero; GitHub lo guarda bien aunque tenga varias líneas). |

Eso es todo lo que preguntabas de "variables/acciones": los tres secrets viven aquí, en
Actions, y los workflows los leen automáticamente. No hay que configurar agents ni nada más.

## Paso 5 — Enciende los workflows

1. Ve a la pestaña **Actions** del repo. Si te pide habilitar los workflows, acéptalo.
2. Verás dos: **"Revisar mensajes (poll)"** y **"Resumen diario (remind)"**.
3. Para probar sin esperar, entra a **"Revisar mensajes (poll)" → Run workflow** (botón
   *Run workflow*). Debe terminar en verde ✅.

## Paso 6 — Estrénalo

En Telegram abre tu bot y manda **`/start`**. En la siguiente corrida (máx. ~5 min, o
córrela a mano como en el paso 5) el bot te responde y quedas registrado para el resumen.

Luego:
- Escríbele cualquier cosa, p. ej. *"Terminar capítulo 3 de la tesis"* → lo anota y te da
  su número.
- `/due 1 2026-07-20` le pone fecha límite al proyecto 1.
- `/prioridad 1 alta` marca prioridad.
- `/list` muestra lo activo, ordenado por urgencia.
- `/done 1` lo marca como hecho.

### Todos los comandos

| Comando | Para qué |
|---|---|
| *(texto libre)* | Agrega un proyecto nuevo a la bandeja |
| `/add nombre` | Agrega un proyecto |
| `/list` | Ver proyectos activos |
| `/todos` | Ver todos (incluye los hechos) |
| `/curso id` | Marcar en curso |
| `/done id` | Marcar hecho ✅ |
| `/pausa id` | Pausar |
| `/due id fecha` | Fecha límite (AAAA-MM-DD o DD/MM/AAAA) |
| `/prioridad id alta\|media\|baja` | Prioridad |
| `/nota id texto` | Agregar una nota (se acumulan con fecha) |
| `/rename id nombre` | Renombrar |
| `/del id` | Borrar |
| `/resumen` | Pedir el recordatorio ahora mismo |

---

## Cosas que conviene saber

- **Latencia:** las respuestas tardan hasta ~5 min (a veces más si GitHub va saturado).
  Es normal con este modelo gratuito.
- **La hora del resumen** se cambia en `.github/workflows/reminder.yml`, línea del `cron`.
  Está en UTC: `0 14 * * *` = 8:00 en CDMX. Para las 7:00 usa `0 13 * * *`.
- **GitHub apaga los workflows programados tras 60 días sin actividad** en el repo. Si un
  día dejan de correr, entra al repo, abre **Actions** y dale **Enable workflow**, o haz
  cualquier commit pequeño. Como tú usarás el bot seguido, difícilmente pasará.
- **Minutos gratis:** repo público = ilimitados. Repo privado = 2,000 min/mes; si lo dejas
  privado, sube el intervalo del poll a cada 15 min (cambia `*/5` por `*/15` en `poll.yml`).

## Seguridad

Compartiste el token del bot en el chat. Si te preocupa, en Telegram abre **@BotFather →
`/revoke`**, genera uno nuevo y actualiza el secret `BOT_TOKEN`. La cuenta de servicio de
Google solo tiene acceso a la hoja que compartiste, a nada más de tu Google. Nunca subas el
`.json` ni un `.env` al repo (el `.gitignore` ya los excluye).

## Probar en tu computadora (opcional)

```
pip install -r requirements.txt
export BOT_TOKEN="..."; export SPREADSHEET_ID="..."; export GOOGLE_CREDENTIALS_FILE="credentials.json"
python bot.py poll      # procesa mensajes una vez
python bot.py remind    # manda el resumen una vez
```
