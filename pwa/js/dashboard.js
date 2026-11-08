"use strict";

if (SGML.exigirRol(["ADMINISTRADOR", "ADMINISTRATIVO"])) {
  const rol = SGML.rolActual();
  document.getElementById("enlace-operarios").hidden = false;
  document.getElementById("enlace-programacion").hidden = rol !== "ADMINISTRADOR";
  document.getElementById("rol-titulo").textContent =
    rol === "ADMINISTRADOR" ? "Administrador" : "Administrativo";
  const fecha = document.getElementById("fecha");
  const filtroCentro = document.getElementById("filtro-centro");
  const jornadas = document.getElementById("jornadas");
  const mensaje = document.getElementById("mensaje");
  const alertaReloj = document.getElementById("alerta-reloj");
  const visor = document.getElementById("visor-foto");
  const fotoAmpliada = document.getElementById("foto-ampliada");
  const urlsImagenes = new Set();
  let filasCargadas = [];
  fecha.value = SGML.fechaLocal();

  function limpiarImagenes() {
    urlsImagenes.forEach((url) => URL.revokeObjectURL(url));
    urlsImagenes.clear();
  }

  function mostrarMensaje(texto) {
    mensaje.textContent = texto;
    mensaje.className = "mensaje error";
    mensaje.hidden = false;
  }

  function mostrarResumen(filas, todasLasFilas) {
    const actividades = filas.flatMap((fila) => fila.actividades);
    const totalSospechosos = todasLasFilas.reduce(
      (total, fila) => total + (fila.eventos_hora_sospechosa || 0), 0,
    );
    const pendientesRevision = actividades.filter((a) => a.estado === "FINALIZADA").length;
    document.getElementById("resumen").innerHTML = `
      <div class="indicador"><strong>${filas.length}</strong><span>operarios con actividad</span></div>
      <div class="indicador"><strong>${actividades.length}</strong><span>actividades programadas</span></div>
      <div class="indicador"><strong>${pendientesRevision}</strong><span>revisiones pendientes</span></div>`;
    alertaReloj.hidden = totalSospechosos === 0;
    alertaReloj.textContent = totalSospechosos
      ? `Alerta de reloj: ${totalSospechosos} eventos con hora sospechosa registrados históricamente en todos los conjuntos. La API no expone aquí el desglose por fecha.`
      : "";
  }

  function actualizarConjuntos(filas) {
    const seleccion = filtroCentro.value;
    const centros = new Map();
    filas.forEach((fila) => {
      (fila.jornadas || []).forEach((jornada) => centros.set(jornada.centro_id, jornada.centro));
      fila.actividades.forEach((actividad) => centros.set(actividad.centro_id, actividad.centro));
    });
    filtroCentro.innerHTML = '<option value="">Todos los conjuntos</option>';
    [...centros.entries()].sort((a, b) => a[1].localeCompare(b[1], "es"))
      .forEach(([id, nombre]) => {
        const opcion = document.createElement("option");
        opcion.value = String(id);
        opcion.textContent = nombre;
        filtroCentro.append(opcion);
      });
    if (centros.has(Number(seleccion))) filtroCentro.value = seleccion;
  }

  function renderizar(filas) {
    limpiarImagenes();
    actualizarConjuntos(filas);
    const centroId = filtroCentro.value;
    const filasFiltradas = filas.map((fila) => ({
      ...fila,
      jornadas: (fila.jornadas || []).filter(
        (jornada) => !centroId || String(jornada.centro_id) === centroId,
      ),
      actividades: fila.actividades.filter(
        (actividad) => !centroId || String(actividad.centro_id) === centroId,
      ),
    })).filter((fila) => !centroId || fila.jornadas.length || fila.actividades.length);
    mostrarResumen(filasFiltradas, filas);
    jornadas.innerHTML = "";
    if (!filasFiltradas.length) {
      jornadas.innerHTML = `<div class="vacio">${centroId
        ? "No hay jornadas ni actividades para el conjunto seleccionado en esta fecha."
        : "No hay jornadas ni actividades para la fecha seleccionada."}</div>`;
      return;
    }

    filasFiltradas.forEach((fila) => {
      const tarjeta = document.createElement("article");
      tarjeta.className = "operario";
      tarjeta.innerHTML = `
        <h2>${SGML.escaparHTML(fila.operario)}</h2>
        <div class="horas">
          ${fila.jornadas.length ? fila.jornadas.map((jornada) => `
            <div class="turno">
              <strong>${SGML.escaparHTML(jornada.centro || "Centro sin nombre")}</strong><br>
              <strong>Entrada:</strong> ${SGML.escaparHTML(jornada.entrada || "Sin registro")}
              · <strong>Salida:</strong> ${SGML.escaparHTML(jornada.salida || "Sin registro")}
            </div>`).join("") : '<span>Sin registro de entrada/salida en este conjunto.</span>'}
          <span><strong>Última sincronización:</strong> ${SGML.escaparHTML(fila.ultima_sincronizacion || "Sin sincronización")}</span>
        </div>
        ${fila.actividades.length ? fila.actividades.map((actividad) => `
          <section class="actividad">
            <h3>${SGML.escaparHTML(actividad.servicio)} · ${SGML.escaparHTML(actividad.centro)}</h3>
            <p class="detalle">
              <span class="estado ${SGML.escaparHTML(actividad.estado)}">${SGML.escaparHTML(actividad.estado)}</span>
              ${actividad.correccion_de_id
                ? ` · Corrección de #${SGML.escaparHTML(actividad.correccion_de_id)}`
                : ""}
              &nbsp; Inicio: ${SGML.escaparHTML(actividad.inicio || "—")} · Fin: ${SGML.escaparHTML(actividad.fin || "—")}
              ${actividad.motivo_correccion
                ? `<br>Motivo: ${SGML.escaparHTML(actividad.motivo_correccion)}`
                : ""}
            </p>
            <div class="miniaturas">
              ${actividad.evidencias.map((momento) => `
                <button class="miniatura" type="button" data-actividad="${SGML.escaparHTML(actividad.id)}"
                  data-momento="${SGML.escaparHTML(momento)}" aria-label="Ver foto ${SGML.escaparHTML(momento)}">
                  <img alt="" loading="lazy"><span>${SGML.escaparHTML(momento)}</span>
                </button>`).join("") || '<span class="sin-fotos">Sin fotos registradas</span>'}
            </div>
          </section>`).join("") : '<p class="detalle">Sin actividades asignadas.</p>'}`;
      jornadas.append(tarjeta);

      tarjeta.querySelectorAll("button.miniatura").forEach((boton) => {
        const ruta = `/api/jornada/actividades/${boton.dataset.actividad}/evidencias/${boton.dataset.momento}`;
        SGML.obtenerImagen(ruta).then((url) => {
          urlsImagenes.add(url);
          boton.querySelector("img").src = url;
        }).catch((error) => {
          boton.querySelector("span").textContent = error.message;
          boton.disabled = true;
        });
      });
    });
  }

  async function cargarSeguimiento() {
    const boton = document.getElementById("actualizar");
    const estado = document.getElementById("actualizado");
    boton.disabled = true;
    estado.textContent = "Consultando…";
    mensaje.hidden = true;
    try {
      const query = new URLSearchParams({ fecha: fecha.value || SGML.fechaLocal() });
      filasCargadas = await SGML.solicitar(`/api/seguimiento?${query}`);
      renderizar(filasCargadas);
      estado.textContent = `Actualizado ${new Date().toLocaleTimeString()}`;
    } catch (error) {
      mostrarMensaje(`No se pudo cargar el tablero: ${error.message}`);
      estado.textContent = "No se pudo actualizar";
    } finally {
      boton.disabled = false;
    }
  }

  jornadas.addEventListener("click", (evento) => {
    const boton = evento.target.closest("button.miniatura");
    if (!boton || boton.disabled) return;
    fotoAmpliada.src = boton.querySelector("img").src;
    fotoAmpliada.alt = `Evidencia ${boton.dataset.momento} de la actividad ${boton.dataset.actividad}`;
    visor.showModal();
  });
  document.getElementById("cerrar-foto").addEventListener("click", () => visor.close());
  document.getElementById("cerrar-sesion").addEventListener("click", SGML.cerrarSesion);
  document.getElementById("actualizar").addEventListener("click", cargarSeguimiento);
  fecha.addEventListener("change", cargarSeguimiento);
  filtroCentro.addEventListener("change", () => renderizar(filasCargadas));
  void cargarSeguimiento();

  window.setInterval(() => {
    if (!document.hidden && !visor.open) void cargarSeguimiento();
  }, 30000);
}
