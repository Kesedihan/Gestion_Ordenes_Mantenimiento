/* SGML - App del operario (PWA offline-first). Patrón MVC en el navegador:
 *   Modelo      -> Almacen (IndexedDB): programación, progreso local y COLA de eventos.
 *   Vista       -> funciones pintar*() que solo generan HTML.
 *   Controlador -> manejadores de eventos de la interfaz (acciones del operario).
 * Escenario E1: todo se registra localmente con UUID + hora del dispositivo.
 * Escenario E2: la cola se envía en orden cuando hay red; el servidor es idempotente.
 */
"use strict";

const operarioId = Number(SGMLAuth.obtener("sgml-operario-id"));

// ============================== MODELO (IndexedDB) ==============================
const Almacen = (() => {
  let db;
  const abrir = () => new Promise((ok, mal) => {
    const req = indexedDB.open(`sgml-operario-${operarioId}`, 1);
    req.onupgradeneeded = () => {
      const d = req.result;
      d.createObjectStore("programacion", { keyPath: "id" });
      d.createObjectStore("progreso", { keyPath: "clave" });
      d.createObjectStore("cola", { keyPath: "seq", autoIncrement: true });
    };
    req.onsuccess = () => { db = req.result; ok(); };
    req.onerror = () => mal(req.error);
  });
  const tx = (tienda, modo, fn) => new Promise((ok, mal) => {
    const t = db.transaction(tienda, modo);
    const r = fn(t.objectStore(tienda));
    t.oncomplete = () => ok(r && r.result);
    t.onerror = () => mal(t.error);
  });
  return {
    abrir,
    todos: (tienda) => tx(tienda, "readonly", (s) => s.getAll()),
    obtener: (tienda, clave) => tx(tienda, "readonly", (s) => s.get(clave)),
    poner: (tienda, valor) => tx(tienda, "readwrite", (s) => s.put(valor)),
    borrar: (tienda, clave) => tx(tienda, "readwrite", (s) => s.delete(clave)),
    reemplazar: (tienda, valores) => tx(tienda, "readwrite", (s) => { s.clear(); valores.forEach((v) => s.put(v)); }),
  };
})();

const uuid = () => (crypto.randomUUID ? crypto.randomUUID() :
  "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)));

// Hora local del celular sin zona horaria (el servidor también guarda la de recepción: D5).
const ahoraLocal = () => {
  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};
const hoy = () => ahoraLocal().slice(0, 10);
const escaparHTML = (valor) => String(valor ?? "").replace(/[&<>"']/g, (caracter) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
}[caracter]));

// Comprime la foto en el celular (≤1280 px, JPEG 70 %) para ahorrar espacio y datos (R2, R9).
async function comprimir(archivo) {
  const imagen = await createImageBitmap(archivo);
  const escala = Math.min(1, 1280 / Math.max(imagen.width, imagen.height));
  const lienzo = document.createElement("canvas");
  lienzo.width = Math.round(imagen.width * escala);
  lienzo.height = Math.round(imagen.height * escala);
  lienzo.getContext("2d").drawImage(imagen, 0, 0, lienzo.width, lienzo.height);
  return new Promise((ok) => lienzo.toBlob(ok, "image/jpeg", 0.7));
}

async function encolarEvento(tipo, datos) {
  await Almacen.poner("cola", { clase: "evento", id: uuid(), tipo, hora_dispositivo: ahoraLocal(), datos });
}
async function encolarFoto(actividad_id, momento, blob) {
  await Almacen.poner("cola", { clase: "foto", id: uuid(), actividad_id, momento, tomada_en: ahoraLocal(), blob });
}
async function marcarProgreso(clave, cambios) {
  const actual = (await Almacen.obtener("progreso", clave)) || { clave };
  await Almacen.poner("progreso", { ...actual, ...cambios });
}

// ============================== SINCRONIZACIÓN (E2) ==============================
let sincronizando = false;
async function sincronizar() {
  if (sincronizando || !operarioId || !SGMLAuth.tieneSesion() || !navigator.onLine) return pintarRed();
  sincronizando = true;
  const avisos = [];
  try {
    const cola = (await Almacen.todos("cola")).sort((a, b) => a.seq - b.seq);
    let i = 0;
    while (i < cola.length) {
      if (cola[i].clase === "foto") {
        const f = cola[i++];
        const datos = new FormData();
        Object.entries({ evento_id: f.id, operario_id: operarioId, actividad_id: f.actividad_id,
          momento: f.momento, tomada_en: f.tomada_en }).forEach(([k, v]) => datos.append(k, v));
        datos.append("foto", f.blob, `${f.momento}.jpg`);
        const r = await SGMLAuth.fetchAutenticado("/api/jornada/evidencias", {
          method: "POST", body: datos,
        });
        if (r.status === 401) {
          window.location.assign("/app/login.html");
          throw new Error("La sesión venció. Inicia sesión para sincronizar.");
        }
        if (!r.ok) throw new Error(`Servidor respondió ${r.status}`);
        await procesarResultado(await r.json(), f, avisos);
      } else {
        const lote = [];
        while (i < cola.length && cola[i].clase === "evento") lote.push(cola[i++]);
        const r = await SGMLAuth.fetchAutenticado("/api/jornada/sincronizar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operario_id: operarioId,
            eventos: lote.map(({ id, tipo, hora_dispositivo, datos }) => ({ id, tipo, hora_dispositivo, datos })) }),
        });
        if (r.status === 401) {
          window.location.assign("/app/login.html");
          throw new Error("La sesión venció. Inicia sesión para sincronizar.");
        }
        if (!r.ok) throw new Error((await r.json()).detail || `Servidor respondió ${r.status}`);
        const resultados = await r.json();
        for (const item of lote) await procesarResultado(resultados.find((x) => x.id === item.id), item, avisos);
      }
    }
    avisos.unshift({ tipo: "info", texto: "Sincronización completa." });
  } catch (e) {
    avisos.unshift({ tipo: "error", texto: `Sincronización interrumpida (${e.message}). Los pendientes se conservan.` });
  } finally {
    sincronizando = false;
    pintarMensajes(avisos);
    await pintar();
  }
}

async function procesarResultado(resultado, item, avisos) {
  // ACEPTADO o DUPLICADO: el servidor ya lo tiene -> se puede borrar de la cola (y la foto del celular).
  // RECHAZADO: se informa el motivo al operario y se retira de la cola para no bloquearla.
  if (resultado.estado === "RECHAZADO")
    avisos.push({ tipo: "error", texto: `Rechazado (${item.tipo || "foto " + item.momento}): ${resultado.motivo}` });
  await Almacen.borrar("cola", item.seq);
}

// ============================== VISTA ==============================
function pintarRed() {
  document.getElementById("red").textContent = navigator.onLine
    ? "● Con conexión" : "○ Sin conexión: todo se guarda en el celular";
}
function pintarMensajes(avisos) {
  document.getElementById("mensajes").innerHTML = avisos
    .map((a) => `<div class="aviso ${a.tipo}">${a.texto}</div>`).join("");
}
const NOMBRE_FOTO = { ANTES: "antes", DURANTE: "durante", DESPUES: "después" };
const ESTADOS_ACTIVIDAD = {
  PROGRAMADA: { clase: "programada", etiqueta: "Programada" },
  EN_CURSO: { clase: "en-curso", etiqueta: "En curso" },
  FINALIZADA: { clase: "finalizada", etiqueta: "Finalizada" },
  ACEPTADA: { clase: "aceptada", etiqueta: "Aceptada" },
  RECHAZADA: { clase: "rechazada", etiqueta: "Rechazada · corrección pendiente" },
};
const paso = (ok, texto) => `<span class="paso ${ok ? "ok" : ""}">${ok ? "✓ " : ""}${texto}</span>`;
const boton = (accion, id, texto, activo) =>
  `<button data-accion="${accion}" data-id="${id}" ${activo ? "" : "disabled"}>${texto}</button>`;
const botonFoto = (id, momento, activo) =>
  `<label class="boton ${activo ? "" : "deshabilitado"}">📷 Foto ${NOMBRE_FOTO[momento]}
     <input type="file" accept="image/*" capture="environment" data-foto="${momento}" data-id="${id}"></label>`;

async function pintar() {
  const fecha = document.getElementById("fecha").value;
  const actividades = (await Almacen.todos("programacion")).filter((a) => a.fecha === fecha);
  const jornada = (await Almacen.obtener("progreso", `jornada-${fecha}`)) || {};
  const pendientes = (await Almacen.todos("cola")).length;
  document.getElementById("cola").textContent = `Pendientes por sincronizar: ${pendientes}`;

  const centros = [...new Map(actividades.map((a) => [a.centro_id, a.centro])).entries()];
  const sesiones = [...(jornada.sesiones || [])];
  if (jornada.entrada && jornada.salida && !sesiones.some(
    (sesion) => sesion.entrada === jornada.entrada && sesion.salida === jornada.salida,
  )) {
    sesiones.push({
      entrada: jornada.entrada,
      salida: jornada.salida,
      centro: jornada.centro,
    });
  }
  const jornadaActiva = Boolean(jornada.entrada && !jornada.salida);
  document.getElementById("jornada").innerHTML = `
    <h2>Jornada del ${fecha}</h2>
    <div class="pasos">${paso(jornadaActiva, "Entrada")}${paso(false, "Salida")}</div>
    ${jornadaActiva ? `<p class="hecho">Entrada en ${jornada.centro} a las ${jornada.entrada.slice(11, 16)}</p>` : `
      <select id="centro">${centros.map(([id, n]) => `<option value="${id}">${n}</option>`).join("")}</select>
      ${boton("entrada", 0, "Registrar entrada", centros.length > 0)}`}
    ${jornadaActiva ? boton("salida", 0, "Registrar salida", true) : ""}
    ${sesiones.length ? `<div class="sub"><strong>Jornadas completadas</strong>${sesiones.map(
      (sesion) => `<p>${sesion.centro} · ${sesion.entrada.slice(11, 16)}–${sesion.salida.slice(11, 16)}</p>`,
    ).join("")}</div>` : ""}`;

  const tarjetas = [];
  for (const a of actividades) {
    const p = (await Almacen.obtener("progreso", `act-${a.id}`)) || {};
    const enCentro = jornada.entrada && !jornada.salida && jornada.centro_id === a.centro_id;
    const estadoServidor = ESTADOS_ACTIVIDAD[a.estado] || ESTADOS_ACTIVIDAD.PROGRAMADA;
    const finalizadaEnServidor = ["FINALIZADA", "ACEPTADA", "RECHAZADA"].includes(a.estado);
    const claseEstado = p.fin && !finalizadaEnServidor ? "finalizada-local" : estadoServidor.clase;
    const etiquetaEstado = a.correccion_de_id
      ? "Corrección solicitada"
      : p.fin && !finalizadaEnServidor
        ? "Finalizada · pendiente de sincronizar"
        : estadoServidor.etiqueta;
    tarjetas.push(`<section class="tarjeta actividad estado-${claseEstado}">
      <div class="actividad-cabecera">
        <h2>${a.tipo_servicio} · ${a.centro}</h2>
        <span class="estado-actividad ${claseEstado}">${etiquetaEstado}</span>
      </div>
      <p class="sub">${a.descripcion}</p>
      ${a.motivo_correccion
        ? `<p class="aviso error">Corrección solicitada por el Supervisor: ${escaparHTML(a.motivo_correccion)}</p>`
        : a.estado === "RECHAZADA" && a.observacion
          ? `<p class="aviso error">Rechazada por el Supervisor: ${escaparHTML(a.observacion)}</p>`
          : ""}
      <div class="pasos">${paso(p.ANTES, "Antes")}${paso(p.inicio, "Inicio")}${paso(p.DURANTE, "Durante")}${paso(p.DESPUES, "Después")}${paso(p.fin, "Fin")}</div>
      ${finalizadaEnServidor
        ? `<p class="resultado-actividad">✓ Trabajo finalizado en servidor${a.estado === "ACEPTADA" ? " y aceptado" : a.estado === "RECHAZADA" ? " · requiere corrección" : ""}</p>`
        : p.fin
          ? `<p class="resultado-actividad pendiente">✓ Finalizada ${p.fin.slice(11, 16)} · pendiente de sincronizar</p>`
          : `
        ${botonFoto(a.id, "ANTES", enCentro && !p.ANTES)}
        ${boton("inicio", a.id, "Iniciar actividad", enCentro && p.ANTES && !p.inicio)}
        ${botonFoto(a.id, "DURANTE", p.inicio && !p.DURANTE)}
        ${botonFoto(a.id, "DESPUES", p.inicio && !p.DESPUES)}
        ${boton("fin", a.id, "Finalizar actividad", p.DURANTE && p.DESPUES && !p.fin)}`}
    </section>`);
  }
  document.getElementById("actividades").innerHTML = tarjetas.join("") ||
    `<section class="tarjeta"><p class="sub">No hay actividades guardadas para esta fecha. Descargue la programación con red.</p></section>`;
}

// ============================== CONTROLADOR ==============================
async function descargarProgramacion() {
  if (!operarioId || !accessToken) {
    window.location.assign("/app/login.html");
    return;
  }
  try {
    const lunes = new Date(); lunes.setDate(lunes.getDate() - ((lunes.getDay() + 6) % 7));
    const desde = `${lunes.getFullYear()}-${String(lunes.getMonth() + 1).padStart(2, "0")}-${String(lunes.getDate()).padStart(2, "0")}`;
    const r = await fetch(`/api/jornada/mi-programacion?desde=${desde}&dias=14`, {
      headers: encabezadosAuth(),
    });
    if (r.status === 401) {
      window.location.assign("/app/login.html");
      return;
    }
    if (!r.ok) throw new Error(`Servidor respondió ${r.status}`);
    const actividades = await r.json();
    await Almacen.reemplazar("programacion", actividades);
    pintarMensajes([{ tipo: "info", texto: `Programación guardada: ${actividades.length} actividades. Ya puede trabajar sin conexión.` }]);
  } catch (e) {
    pintarMensajes([{ tipo: "error", texto: `No se pudo descargar (${e.message}).` }]);
  }
  pintar();
}

document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("button[data-accion]");
  if (!b) return;
  const fecha = document.getElementById("fecha").value, id = Number(b.dataset.id), hora = ahoraLocal();
  if (b.dataset.accion === "entrada") {
    const sel = document.getElementById("centro");
    const centro_id = Number(sel.value);
    const clave = `jornada-${fecha}`;
    const actual = (await Almacen.obtener("progreso", clave)) || {};
    const sesiones = [...(actual.sesiones || [])];
    if (actual.entrada && actual.salida && !sesiones.some(
      (sesion) => sesion.entrada === actual.entrada && sesion.salida === actual.salida,
    )) {
      sesiones.push({
        entrada: actual.entrada,
        salida: actual.salida,
        centro: actual.centro,
      });
    }
    await encolarEvento("ENTRADA", { centro_id });
    await Almacen.poner("progreso", {
      ...actual,
      clave,
      sesiones,
      entrada: hora,
      salida: null,
      centro_id,
      centro: sel.selectedOptions[0].text,
    });
  } else if (b.dataset.accion === "salida") {
    await encolarEvento("SALIDA", {});
    const clave = `jornada-${fecha}`;
    const actual = (await Almacen.obtener("progreso", clave)) || {};
    await Almacen.poner("progreso", {
      ...actual,
      sesiones: [
        ...(actual.sesiones || []),
        {
          entrada: actual.entrada,
          salida: hora,
          centro: actual.centro,
        },
      ],
      entrada: null,
      salida: null,
      centro_id: null,
      centro: null,
    });
  } else if (b.dataset.accion === "inicio") {
    await encolarEvento("INICIO_ACTIVIDAD", { actividad_id: id });
    await marcarProgreso(`act-${id}`, { inicio: hora });
  } else if (b.dataset.accion === "fin") {
    await encolarEvento("FIN_ACTIVIDAD", { actividad_id: id });
    await marcarProgreso(`act-${id}`, { fin: hora });
  }
  await pintar();
  sincronizar(); // si hay red, envía de inmediato; si no, queda en cola
});

document.addEventListener("change", async (ev) => {
  const entrada = ev.target;
  if (entrada.id === "fecha") return pintar();
  if (!entrada.dataset.foto || !entrada.files.length) return;
  const id = Number(entrada.dataset.id), momento = entrada.dataset.foto;
  const blob = await comprimir(entrada.files[0]);
  await encolarFoto(id, momento, blob);
  await marcarProgreso(`act-${id}`, { [momento]: ahoraLocal() });
  pintarMensajes([{ tipo: "info", texto: `Foto ${NOMBRE_FOTO[momento]} guardada (${Math.round(blob.size / 1024)} KB).` }]);
  await pintar();
  sincronizar();
});

document.getElementById("descargar").addEventListener("click", descargarProgramacion);
document.getElementById("sincronizar").addEventListener("click", sincronizar);
document.getElementById("cerrar-sesion").addEventListener("click", async () => {
  const pendientes = await Almacen.todos("cola");
  if (pendientes.length && !window.confirm(
    `Hay ${pendientes.length} elementos pendientes de sincronizar. ` +
    "Se conservarán en este dispositivo, pero debes volver a iniciar sesión para enviarlos. ¿Cerrar sesión?",
  )) return;

  SGMLAuth.limpiar();
  window.location.assign("/app/login.html");
});
window.addEventListener("online", () => { pintarRed(); sincronizar(); });
window.addEventListener("offline", pintarRed);

(async function iniciar() {
  if (!operarioId || !SGMLAuth.tieneSesion() || SGMLAuth.obtener("sgml-rol") !== "OPERARIO") {
    window.location.replace("/app/login.html");
    return;
  }
  document.getElementById("nombre-operario").textContent =
    SGMLAuth.obtener("sgml-nombre-usuario") || "Operario";
  document.getElementById("fecha").value = hoy();
  await Almacen.abrir();
  pintarRed();
  await pintar();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");
  sincronizar();
})();
