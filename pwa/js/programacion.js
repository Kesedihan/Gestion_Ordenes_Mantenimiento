"use strict";

if (SGML.exigirRol(["ADMINISTRADOR"])) {
  const formAsignacion = document.getElementById("form-asignacion");
  const formControls = {
    semana: document.getElementById("semana-inicio"),
    operario: document.getElementById("operario"),
    centro: document.getElementById("centro"),
    fecha: document.getElementById("fecha-asignacion"),
    servicio: document.getElementById("servicio"),
    descripcion: document.getElementById("descripcion"),
  };
  const mensaje = document.getElementById("mensaje");
  const listaAsignaciones = document.getElementById("asignaciones");
  const filasProgramaciones = document.getElementById("filas-programaciones");
  let asignaciones = [];
  let semanaAsignaciones = null;
  let operarios = [];
  let centros = [];

  function mostrarMensaje(texto, tipo = "ok") {
    mensaje.textContent = texto;
    mensaje.className = `mensaje ${tipo}`;
    mensaje.hidden = false;
  }

  function limpiarMensaje() {
    mensaje.textContent = "";
    mensaje.hidden = true;
  }

  function lunesDeSemana(fecha) {
    const lunes = new Date(`${fecha}T00:00:00`);
    lunes.setDate(lunes.getDate() - ((lunes.getDay() + 6) % 7));
    const dos = (valor) => String(valor).padStart(2, "0");
    return `${lunes.getFullYear()}-${dos(lunes.getMonth() + 1)}-${dos(lunes.getDate())}`;
  }

  function actualizarRangoFecha() {
    const inicio = formControls.semana.value;
    if (!inicio) return;
    const lunes = new Date(`${inicio}T00:00:00`);
    const domingo = new Date(lunes);
    domingo.setDate(lunes.getDate() + 6);
    const dos = (valor) => String(valor).padStart(2, "0");
    const fechaMinima = `${lunes.getFullYear()}-${dos(lunes.getMonth() + 1)}-${dos(lunes.getDate())}`;
    const fechaMaxima = `${domingo.getFullYear()}-${dos(domingo.getMonth() + 1)}-${dos(domingo.getDate())}`;
    formControls.fecha.min = fechaMinima;
    formControls.fecha.max = fechaMaxima;
    if (!formControls.fecha.value || formControls.fecha.value < fechaMinima
        || formControls.fecha.value > fechaMaxima) {
      formControls.fecha.value = fechaMinima;
    }
  }

  function pintarAsignaciones() {
    listaAsignaciones.innerHTML = asignaciones.map((asignacion, indice) => {
      const operario = operarios.find((item) => item.id === asignacion.operario_id);
      const centro = centros.find((item) => item.id === asignacion.centro_id);
      return `<li class="asignacion">
        <span>${SGML.escaparHTML(asignacion.fecha)} · ${SGML.escaparHTML(operario?.nombre)}
          · ${SGML.escaparHTML(centro?.nombre)} · ${SGML.escaparHTML(asignacion.tipo_servicio)}
          · ${SGML.escaparHTML(asignacion.descripcion)}</span>
        <button class="secundario" type="button" data-quitar="${indice}">Quitar</button>
      </li>`;
    }).join("");
    document.getElementById("guardar-borrador").disabled = asignaciones.length === 0;
  }

  function pintarProgramaciones(programaciones) {
    filasProgramaciones.innerHTML = programaciones.map((programacion) => {
      const detalles = programacion.asignaciones.map((asignacion) => {
        const operario = operarios.find((item) => item.id === asignacion.operario_id);
        const centro = centros.find((item) => item.id === asignacion.centro_id);
        return `${SGML.escaparHTML(asignacion.fecha)}: ${SGML.escaparHTML(operario?.nombre || `Operario ${asignacion.operario_id}`)} — ${SGML.escaparHTML(centro?.nombre || `Centro ${asignacion.centro_id}`)} / ${SGML.escaparHTML(asignacion.tipo_servicio)} / ${SGML.escaparHTML(asignacion.descripcion)}`;
      });
      return `<tr>
        <td>${SGML.escaparHTML(programacion.semana_inicio)}</td>
        <td><span class="estado ${SGML.escaparHTML(programacion.estado)}">${SGML.escaparHTML(programacion.estado)}</span></td>
        <td>${detalles.join("<br>")}</td>
        <td>${SGML.escaparHTML(programacion.publicada_en || "—")}</td>
        <td>${programacion.estado === "BORRADOR"
          ? `<button class="publicar" type="button" data-publicar="${SGML.escaparHTML(programacion.id)}">Publicar</button>`
          : "Bloqueada"}</td>
      </tr>`;
    }).join("");
    document.getElementById("sin-programaciones").hidden = programaciones.length > 0;
  }

  async function cargarProgramaciones() {
    const boton = document.getElementById("actualizar");
    boton.disabled = true;
    try {
      const [programaciones, catalogos] = await Promise.all([
        SGML.solicitar("/api/programaciones"),
        SGML.solicitar("/api/programaciones/catalogos"),
      ]);
      operarios = catalogos.operarios;
      centros = catalogos.centros;
      document.getElementById("operario").innerHTML = operarios.map((operario) =>
        `<option value="${SGML.escaparHTML(operario.id)}">${SGML.escaparHTML(operario.nombre)}</option>`
      ).join("");
      document.getElementById("centro").innerHTML = centros.map((centro) =>
        `<option value="${SGML.escaparHTML(centro.id)}">${SGML.escaparHTML(centro.nombre)}</option>`
      ).join("");
      pintarAsignaciones();
      pintarProgramaciones(programaciones);
    } catch (error) {
      mostrarMensaje(`No se pudo cargar la programación: ${error.message}`, "error");
    } finally {
      boton.disabled = false;
    }
  }

  async function guardarBorrador() {
    const boton = document.getElementById("guardar-borrador");
    if (!asignaciones.length) return;
    boton.disabled = true;
    try {
      await SGML.solicitar("/api/programaciones", {
        method: "POST",
        body: JSON.stringify({
          semana_inicio: formControls.semana.value,
          asignaciones,
        }),
      });
      asignaciones = [];
      pintarAsignaciones();
      mostrarMensaje("Borrador semanal guardado.");
      await cargarProgramaciones();
    } catch (error) {
      mostrarMensaje(`No se pudo guardar el borrador: ${error.message}`, "error");
    } finally {
      boton.disabled = asignaciones.length === 0;
    }
  }

  async function publicar(programacionId, boton) {
    if (!window.confirm("Al publicar, la programación quedará bloqueada y se encolarán los correos. ¿Continuar?")) return;
    boton.disabled = true;
    try {
      await SGML.solicitar(`/api/programaciones/${programacionId}/publicar`, {
        method: "POST",
      });
      mostrarMensaje("Programación publicada. Actividades y correos quedaron encolados.");
      await cargarProgramaciones();
    } catch (error) {
      mostrarMensaje(`No se pudo publicar: ${error.message}`, "error");
    } finally {
      boton.disabled = false;
    }
  }

  formAsignacion.addEventListener("submit", (evento) => {
    evento.preventDefault();
    const semana = formControls.semana.value;
    if (!semana) return;
    if (lunesDeSemana(semana) !== semana) {
      mostrarMensaje("La semana debe comenzar un lunes.", "error");
      formControls.semana.focus();
      return;
    }
    if (semanaAsignaciones && semanaAsignaciones !== semana) {
      mostrarMensaje("No mezcles semanas en el mismo borrador. Guarda o limpia las asignaciones actuales.", "error");
      return;
    }
    semanaAsignaciones = semana;
    asignaciones.push({
      operario_id: Number(formControls.operario.value),
      centro_id: Number(formControls.centro.value),
      fecha: formControls.fecha.value,
      tipo_servicio: formControls.servicio.value.trim().toUpperCase(),
      descripcion: formControls.descripcion.value.trim(),
    });
    formControls.servicio.value = "";
    formControls.descripcion.value = "";
    pintarAsignaciones();
    limpiarMensaje();
  });

  listaAsignaciones.addEventListener("click", (evento) => {
    const boton = evento.target.closest("button[data-quitar]");
    if (!boton) return;
    asignaciones.splice(Number(boton.dataset.quitar), 1);
    if (!asignaciones.length) semanaAsignaciones = null;
    pintarAsignaciones();
  });

  filasProgramaciones.addEventListener("click", (evento) => {
    const boton = evento.target.closest("button[data-publicar]");
    if (boton) void publicar(Number(boton.dataset.publicar), boton);
  });
  document.getElementById("limpiar-asignaciones").addEventListener("click", () => {
    asignaciones = [];
    semanaAsignaciones = null;
    pintarAsignaciones();
  });
  document.getElementById("guardar-borrador").addEventListener("click", guardarBorrador);
  document.getElementById("actualizar").addEventListener("click", cargarProgramaciones);
  document.getElementById("cerrar-sesion").addEventListener("click", SGML.cerrarSesion);
  formControls.semana.value = lunesDeSemana(SGML.fechaLocal());
  actualizarRangoFecha();
  formControls.semana.addEventListener("change", actualizarRangoFecha);
  void cargarProgramaciones();
}
