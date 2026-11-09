# SGML — Sistema de Gestión de Mantenimiento Locativo

SGML es una aplicación web instalable (PWA) para organizar el mantenimiento de
centros de trabajo. El backend está construido con FastAPI, SQLAlchemy y una
arquitectura hexagonal modular; el frontend usa HTML, CSS y JavaScript sin
frameworks, con IndexedDB para el trabajo sin conexión.

## Contenido

- [Módulos](#módulos)
- [Preparación local](#preparación-local)
- [Cuentas y datos locales](#cuentas-y-datos-locales)
- [Recorrido para probar el aplicativo](#recorrido-para-probar-el-aplicativo)
- [Programación y correo](#programación-y-correo)
- [Pruebas](#pruebas)
- [Arquitectura y estructura](#arquitectura-y-estructura)
- [Dónde se aplica cada principio](#dónde-se-aplica-cada-principio)
- [Limitaciones conocidas](#limitaciones-conocidas)

## Módulos

| Módulo | Funcionalidad principal | Vistas |
| --- | --- | --- |
| Identidad | Login OAuth 2.0, JWT, contraseñas bcrypt y roles Administrador, Administrativo, Supervisor y Operario. | `/app/login.html` |
| M1 — Hojas de vida | Registrar y listar operarios, editar datos de contacto y activar o inactivar su perfil. | `/app/backoffice.html` |
| M2 — Jornada | Registrar entrada y salida, consultar trabajos, guardar fotos antes/durante/después sin conexión, sincronizar y revisar actividades. | `/app/`, `/app/supervisor.html` |
| Seguimiento | Consultar jornadas, estados, evidencias y alertas de reloj; refresca cada 30 segundos. | `/app/dashboard.html` |
| M3 — Programación | Crear y publicar asignaciones semanales; encolar correos en la misma transacción de publicación. | `/app/programacion.html` |

## Preparación local

Requisitos: Python 3.11 o superior y pip. Para enviar correos en la demostración
se puede usar MailHog con Docker; el resto de la aplicación usa dependencias
de `requirements.txt`.

En PowerShell, desde la raíz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# Recomendado: genera un secreto para esta sesión local.
$env:SGML_JWT_SECRET = (python -c "import secrets; print(secrets.token_urlsafe(32))")

# Crea perfiles vinculados, tareas y una programación ya publicada.
python -m app.preparar_pruebas

# Inicia la API y el frontend en http://127.0.0.1:8000
# Si la aplicación ya está activa, reutiliza su URL en lugar de iniciar otra copia.
python -m uvicorn app.main:app --reload --port 8000
```

Después abre <http://127.0.0.1:8000/app/login.html>. La documentación de la
API está en <http://127.0.0.1:8000/docs>.

En el login, **Recordarme en este dispositivo** conserva los tokens en ese
navegador para volver a abrir la PWA, incluso sin conexión, después de haber
iniciado sesión y descargado la programación. Si se deja desmarcado, los tokens
solo duran mientras siga abierta la pestaña del navegador. No marques la opción
en dispositivos compartidos. El access token se renueva automáticamente con
el refresh token cuando hay conexión; el refresh token vence a los 30 días.

La aplicación usa `sgml.db` y la carpeta `evidencias/` en la raíz del proyecto
por defecto. Se pueden cambiar con `SGML_BD_URL` y `SGML_EVIDENCIAS`. Si no se
define `SGML_JWT_SECRET`, en desarrollo se genera uno temporal al iniciar la
API; al reiniciar, los tokens anteriores dejan de ser válidos y hay que volver
a iniciar sesión.

## Cuentas y datos locales

`python -m app.preparar_pruebas` es una carga explícita, repetible y exclusiva
para entornos locales. Prepara tres centros, tres hojas de vida, seis cuentas
y sus vínculos, actividades finalizadas con evidencias ilustrativas, una
jornada con una alerta de reloj y asignaciones para cada operario. La carga
publica la programación semanal en la base de datos; no deja esa programación
en estado `BORRADOR`. También normaliza las cuentas locales antiguas `demo.*`
si existen. No elimina datos ajenos a la carga y rechaza la ejecución si
`SGML_ENV=production`.

Las credenciales siguientes son **solo para la base local de pruebas**. Son
cuentas funcionales para recorrer las vistas y no deben desplegarse ni
reutilizarse en producción.

| Perfil | Usuario | Contraseña | Acceso |
| --- | --- | --- | --- |
| Administrador | `sgml.admin` | `Admin2026!` | Programación semanal |
| Administrativo | `sgml.gestion` | `Gestion2026!` | Tablero y hojas de vida |
| Supervisor | `sgml.supervisor` | `Supervisor2026!` | Revisión de actividades |
| Operario — Carlos Perdomo | `operario.carlos` | `Carlos2026!` | Su PWA y programación |
| Operario — Luisa Cabrera | `operario.luisa` | `Luisa2026!` | Su PWA y programación |
| Operario — Jorge Martínez | `operario.jorge` | `Jorge2026!` | Su PWA y programación |

Cada cuenta de Operario está vinculada en la base a su hoja de vida. Después
del login, la PWA solicita `GET /api/jornada/mi-programacion`; no pide ni
acepta que se escriba un ID. La API deriva el operario del token autenticado y
rechaza consultas o sincronizaciones asociadas a otra hoja de vida. La cola y
el caché offline de IndexedDB también se guardan por separado para cada
operario en el dispositivo.

El modelo actual representa los lugares donde se presta el servicio como
`centros_trabajo` (por ejemplo, “Conjunto Reservas del Río” y “Conjunto Torres
de Altamira”); aún no existe una entidad separada para una empresa cliente.
Las fotos presembradas son imágenes gráficas ficticias, diferenciadas por
momento, no fotografías de personas ni de trabajos reales.

## Recorrido para probar el aplicativo

### 1. Administrar hojas de vida

1. Inicia sesión como `sgml.gestion`.
2. En el tablero, selecciona **Gestión de operarios** o abre
   <http://127.0.0.1:8000/app/backoffice.html>.
3. Revisa las tres hojas de vida, registra un operario nuevo con correo
   institucional, edita su teléfono/correo y prueba activar e inactivar.
4. El caso de uso valida que el correo termine en el dominio institucional
   configurado, `@mantenimiento.com.co` por defecto. El formato también se
   valida en la entidad y en el formulario.

### 2. Crear y publicar una programación

1. Inicia sesión como `sgml.admin` y abre **Programación semanal** o
   <http://127.0.0.1:8000/app/programacion.html>.
2. La carga local ya deja publicada la próxima programación, con tareas para
   los tres operarios. También puedes crear otra programación si esa semana
   todavía no existe.
3. Al publicar una programación, queda bloqueada, sus actividades se crean
   para la PWA y se encola un mensaje por operario.
4. El rol Administrativo puede consultar el tablero, pero la administración
   de programaciones está reservada al Administrador.

### 3. Probar la jornada offline-first

1. Inicia sesión con cualquiera de las tres cuentas `operario.*`; si quieres
   reabrir la PWA después de cerrar el navegador, marca **Recordarme en este
   dispositivo**. Pulsa **Actualizar mi programación**. La aplicación
   identifica al operario por su cuenta. Para ver las tareas publicadas, elige
   una fecha de la semana programada.
2. Registra entrada, fotos y actividad. En un teléfono, la captura usa la
   cámara; en escritorio se puede escoger una imagen desde el disco.
3. Para simular desconexión, abre las herramientas de desarrollador del
   navegador, selecciona *Network → Offline* y registra eventos/fotos. Se
   guardan localmente en IndexedDB.
4. Vuelve a activar la red o pulsa **Sincronizar ahora**. Los eventos se
   sincronizan en orden y el servidor acepta duplicados de manera idempotente.
5. Si el navegador no tiene cámara, puedes elegir imágenes locales. La carga
   también incluye actividades finalizadas con evidencias gráficas ilustrativas
   para recorrer el flujo del Supervisor y del tablero.

### 4. Revisar como Supervisor

1. Inicia sesión como `sgml.supervisor` y abre
   <http://127.0.0.1:8000/app/supervisor.html>.
2. En la fecha actual hay actividades finalizadas con evidencias **ANTES**,
   **DURANTE** y **DESPUÉS**.
3. Acepta una. Rechaza la otra escribiendo una observación; el rechazo sin
   observación se valida y no se envía.
4. Al rechazar, el registro original conserva su estado, observación y fotos.
   El sistema crea otra actividad vinculada para el mismo Operario y con la
   observación como instrucción de corrección; la nueva actividad empieza en
   estado `PROGRAMADA` y tiene evidencias propias.
5. El Operario debe volver a la PWA con conexión y pulsar **Actualizar mi
   programación** para descargar la tarea de corrección. La completa con el
   mismo flujo de entrada, fotos, inicio y finalización; después vuelve a la
   lista de revisión del Supervisor para que sea aceptada o rechazada. Cada
   rechazo sucesivo crea una nueva tarea enlazada, sin sobrescribir los
   registros ni evidencias anteriores.
6. La actividad revisada deja de aparecer en pendientes; el tablero conserva
   tanto la actividad rechazada como sus correcciones y motivos. Volver a
   ejecutar la carga no revierte decisiones ya realizadas.

### 5. Consultar el tablero

1. Inicia sesión como `sgml.gestion` y abre
   <http://127.0.0.1:8000/app/dashboard.html>.
2. Selecciona la fecha actual para ver una jornada, actividades, estados e
   imágenes de ejemplo. Una alerta de reloj está sembrada intencionalmente para
   que se vea el indicador.
3. Usa el filtro **Conjunto** para mostrar solo las entradas/salidas y
   actividades de ese centro de trabajo, o selecciona **Todos los conjuntos**.
   Las jornadas muestran centro, entrada y salida por separado, incluso si un
   operario estuvo en más de un conjunto ese día.
4. El tablero consulta de nuevo cada 30 segundos mientras la pestaña está
   visible. El contador de eventos sospechosos es histórico, incluye todos los
   conjuntos y no está limitado a la fecha seleccionada.

### 6. Ver los correos de publicación (opcional)

En una terminal adicional, inicia MailHog:

```powershell
docker run --rm -p 1025:1025 -p 8025:8025 mailhog/mailhog
```

En otra terminal, desde la raíz del proyecto, ejecuta el trabajador:

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.programacion.trabajador_outbox
```

MailHog muestra los mensajes en <http://127.0.0.1:8025>. El trabajador usa por
defecto SMTP en `localhost:1025`. Variables opcionales:
`SGML_SMTP_HOST`, `SGML_SMTP_PORT`, `SGML_SMTP_FROM`, `SGML_SMTP_USER`,
`SGML_SMTP_PASSWORD`, `SGML_SMTP_STARTTLS` y `SGML_OUTBOX_POLL_SECONDS`.

Para probar la PWA desde un celular físico, se requiere HTTPS fuera de
`localhost` para habilitar Service Worker y cámara.

## Programación y correo

- La semana comienza el lunes. La regla de dominio valida que todas las
  asignaciones caigan en sus siete días y que no existan asignaciones
  duplicadas. Solo se puede crear una programación por semana.
- El Administrador puede crear, listar y publicar. No hay edición después de
  publicar: el agregado cambia de `BORRADOR` a `PUBLICADA` mediante una
  transición de dominio.
- En una misma sesión/transacción SQL se guarda la publicación, se generan las
  actividades de Jornada y se insertan mensajes Outbox. Si falla la operación,
  la petición hace rollback.
- El worker de correo es un proceso separado del servidor web. Conserva los
  mensajes con fallo SMTP y reintenta con espera exponencial desde 30 segundos
  hasta 6 horas. El diseño usa una sola instancia del worker por base de datos.
- La entrega SMTP es *at-least-once*: si el servidor acepta un correo y el
  worker se detiene antes de marcar el mensaje como enviado, puede reenviarlo
  cuando venza el lease de dos minutos.

## Pruebas

Desde un entorno virtual con las dependencias instaladas:

```powershell
python -m pytest -v
```

Las pruebas usan SQLite en memoria y datos aislados; no necesitan la base local
de demostración. Las pruebas de extremo a extremo cubren identidad,
autorización, hojas de vida, sincronización/evidencias, revisión, publicación y
reintentos del Outbox.

## Arquitectura y estructura

El proyecto es un monolito modular. La aplicación HTTP compone módulos
independientes y cada módulo mantiene separados el dominio, los casos de uso,
los puertos y sus adaptadores.

```text
app/
  main.py                 Composición HTTP, routers y errores de negocio
  contenedor.py           Raíz de composición e inyección de dependencias
  dependencias.py         Sesión y transacción por petición
  semilla.py              Catálogos, operarios y asignaciones base de ejemplo
  preparar_pruebas.py     Cuentas vinculadas, jornadas y programación publicada
  compartido/             Base ORM, errores y puerto de reloj
  identidad/              Roles, bcrypt, JWT y repositorio de usuarios
  hojas_vida/             M1: dominio, puertos, casos de uso, SQL y API
  jornada/                M2: dominio, manejadores, casos de uso, SQL y API
  programacion/            M3: programación, catálogo, Outbox, SMTP y worker
pwa/
  login.html               Inicio de sesión
  backoffice.html          Hojas de vida
  supervisor.html          Revisión y evidencias
  dashboard.html           Seguimiento operativo
  programacion.html        Programación semanal
  index.html, app.js        Jornada offline-first e IndexedDB
tests/                     Pruebas unitarias e integración de API
```

## Dónde se aplica cada principio

Los siguientes ejemplos apuntan a implementaciones concretas del proyecto.
Las capas permiten localizar cada regla, responsabilidad o contrato; no son
solo nombres aplicados a carpetas.

### Encapsulación

Oculta el estado interno y permite cambiarlo mediante operaciones que mantienen
las reglas del negocio. En [`ProgramacionSemanal`](app/programacion/dominio.py),
`_estado` no tiene setter público: `publicar()` realiza la transición una sola
vez y guarda la fecha. En [`Actividad`](app/jornada/dominio.py), `iniciar()`,
`finalizar()` y `revisar()` controlan estado, horas, evidencias y observaciones.
Así los adaptadores no asignan libremente estados inconsistentes.

### Bajo acoplamiento

Un módulo conoce lo mínimo necesario de otro, y el detalle se traduce en un
adaptador. [`DirectorioOperariosDesdeHojasVida`](app/contenedor.py) implementa
el puerto [`DirectorioOperarios`](app/jornada/puertos.py): Jornada solicita
`esta_activo(id)` o `nombre(id)` sin importar tablas o clases de persistencia
de Hojas de vida. Se puede cambiar el origen de esos datos sin cambiar los
casos de uso de Jornada.

### Alta cohesión / SRP

Cada unidad agrupa tareas relacionadas y tiene un motivo principal para
cambiar. En [`manejadores.py`](app/jornada/manejadores.py),
`ManejadorEntrada` procesa entradas y `ManejadorSalida` procesa salidas.
[`RepositorioOutboxSQL`](app/programacion/infraestructura.py) reclama y guarda
mensajes; [`EmisorSMTP`](app/programacion/correo.py) se conecta a SMTP. Una
cambio en el transporte de correo no requiere cambiar el dominio ni el
repositorio.

### DRY

Una regla compartida se implementa una vez para reducir divergencias.
[`_ManejadorActividad._actividad_de()`](app/jornada/manejadores.py) concentra
la carga de actividad y la verificación de asignación, reutilizadas por inicio
y fin. [`ProcesadorIdempotente.procesar()`](app/jornada/casos_uso.py) comparte
la detección de duplicados y el registro de resultados entre eventos y
evidencias.

### SoC — Separación de responsabilidades

La lógica de negocio, los contratos, la infraestructura y el transporte HTTP
se mantienen en componentes distintos. En
[`programacion/`](app/programacion/), `dominio.py` define reglas y entidades,
`casos_uso.py` orquesta escenarios, `puertos.py` declara contratos,
`infraestructura.py` implementa persistencia, `correo.py` implementa SMTP y
`api.py` traduce HTTP. Una regla semanal no necesita importar FastAPI.

### Ley de Demeter

Un objeto pide a sus colaboradores lo que necesita, sin navegar estructuras
internas de otros módulos. [`ConsultarSeguimiento.ejecutar()`](app/jornada/casos_uso.py)
obtiene el nombre mediante `_directorio.nombre(operario_id)`. No accede a una
cadena de propiedades internas del agregado de Hojas de vida.

### KISS

Se prefiere la solución sencilla que satisface la necesidad actual.
[`trabajador_outbox.py`](app/programacion/trabajador_outbox.py) es un proceso
independiente que consulta el Outbox y [`ProcesarOutbox`](app/programacion/casos_uso.py)
gestiona los reintentos. Para este sistema se evita desplegar un broker
adicional; SMTP y la tabla persistente resuelven el flujo.

### IoC / Hollywood

El flujo de alto nivel no busca ni crea sus detalles: el ensamblador se los
proporciona. [`Contenedor.casos_uso_programacion()`](app/contenedor.py) crea
repositorios SQL y los inyecta a los casos de uso; los endpoints obtienen los
casos mediante `Depends`. `CrearProgramacion` y `PublicarProgramacion` reciben
sus colaboradores por constructor, sin instanciar sesiones, SQL o SMTP.

### OCP — Abierto/cerrado

El comportamiento se extiende con nuevos componentes sin editar el flujo
estable. [`SincronizarLote.ejecutar()`](app/jornada/casos_uso.py) busca
`evento.tipo` en un diccionario de manejadores. Para admitir otro tipo de
evento se implementa un manejador y se registra en
[`Contenedor.casos_uso_jornada()`](app/contenedor.py), sin añadir una cadena de
`if/elif` al caso de uso.

### LSP — Sustitución de Liskov

Una implementación de un contrato se puede sustituir por otra conservando el
comportamiento esperado. [`RelojSistema`](app/compartido/reloj.py) y
[`RelojFijo`](app/compartido/reloj.py) ofrecen el mismo método `ahora()` del
puerto `Reloj`; los casos de uso pueden usar el reloj real o el reloj fijo en
pruebas. De igual manera, los repositorios SQL implementan sus puertos.

### ISP — Segregación de interfaces

Los consumidores no dependen de operaciones que no usan.
[`jornada/puertos.py`](app/jornada/puertos.py) define contratos separados para
`RepositorioActividades`, `RepositorioJornadas`, `RegistroEventos`,
`RepositorioEvidencias`, `AlmacenArchivos` y `DirectorioOperarios`. Por
ejemplo, el manejador de entrada recibe el repositorio de jornadas, no un
repositorio general con métodos de fotos, correo y usuarios.

### DIP — Inversión de dependencias

La política de negocio depende de abstracciones y no de detalles de
infraestructura. [`PublicarProgramacion`](app/programacion/casos_uso.py)
depende de `RepositorioProgramaciones`, `CatalogoProgramacion` y
`RepositorioOutbox`, definidos en
[`programacion/puertos.py`](app/programacion/puertos.py). SQLAlchemy es una
implementación concreta en
[`RepositorioProgramacionesSQL`](app/programacion/infraestructura.py);
cambiarla no obliga a modificar el caso de uso.

## Limitaciones conocidas

- Para el primer inicio de sesión y la primera descarga de programación se
  requiere conexión. El modo **Recordarme** permite reabrir la sesión local en
  ese mismo navegador; no permite autenticar una cuenta nueva sin conexión.
- El refresh token vence a los 30 días. Si vence mientras no hay conexión, la
  PWA puede abrirse y seguir guardando trabajo local si conserva la sesión
  recordada, pero será necesario iniciar sesión con red antes de sincronizar.
- La PWA consulta su programación y sincroniza eventos/evidencias con el JWT;
  la API verifica que el ID de la carga coincida con el operario vinculado al
  token. Los endpoints de Hojas de vida todavía necesitan autorización por
  rol en el servidor. No exponerlos públicamente sin completarla.
- La alerta de reloj muestra el total histórico informado por la API; no hay
  desglose por la fecha elegida en el tablero.
- Las evidencias preparadas para el recorrido son imágenes gráficas
  ilustrativas, no fotografías de trabajos reales.
- SQLite y almacenamiento local de fotos son adecuados para pruebas locales.
  Para producción se requiere PostgreSQL, almacenamiento de objetos como
  MinIO, HTTPS, un secreto persistente y una revisión completa de
  autorizaciones.
