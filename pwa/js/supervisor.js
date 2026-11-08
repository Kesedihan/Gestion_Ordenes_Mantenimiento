"use strict";

if (SGML.exigirRol(["SUPERVISOR"])) {
  const MOMENTOS = ["ANTES", "DURANTE", "DESPUES"];
  const ETIQUETAS = { ANTES: "Antes", DURANTE: "Durante", DESPUES: "Después" };
  const fecha = document.getElementById("fecha");
  const lista = document.getElementById("actividades");
  const mensaje = document.getElementById("mensaje");
  const urlsImagenes = new Set();
  fecha.value = SGML.fechaLocal();

  function mostrarMensaje(texto, tipo = "ok") {
    mensaje.textContent = texto;
    mensaje.className = `mensaje ${tipo}`;
    mensaje.hidden = false;
  }

  function limpiarImagenes() {
    urlsImagenes.forEach((url) => URL.revokeObjectURL(url));
    urlsImagenes.clear();
  }

  function renderizar(actividades) {
    limpiarImagenes();
    lista.innerHTML = "";
    if (!actividades.length) {
      lista.innerHTML = '<div class="vacio">No hay actividades finalizadas pendientes de revisión para esta fecha.</div>';
      return;
    }

    actividades.forEach((actividad) => {
      const tarjeta = document.createElement("article");
      tarjeta.className = "tarjeta";
      tarjeta.innerHTML = `
        <div class="cabecera">
          <h2>${SGML.escaparHTML(actividad.operario)} · ${SGML.escaparHTML(actividad.tipo_servicio)}</h2>
          <span class="estado-carga">Actividad #${SGML.escaparHTML(actividad.id)}</span>
        </div>
        <p class="sub">${SGML.escaparHTML(actividad.centro)} · ${SGML.escaparHTML(actividad.descripcion)}
          <br>Inicio: ${SGML.escaparHTML(actividad.hora_inicio || "—")} · Fin: ${SGML.escaparHTML(actividad.hora_fin || "—")}</p>
        ${actividad.correccion_de_id
          ? `<p class="mensaje error">Revisión de una corrección de la actividad #${SGML.escaparHTML(actividad.correccion_de_id)}: ${SGML.escaparHTML(actividad.motivo_correccion || "")}</p>`
          : ""}
        <div class="fotos">
          ${MOMENTOS.map((momento) => `
            <section class="foto">
              <h3>${ETIQUETAS[momento]}</h3>
              ${actividad.evidencias.includes(momento)
                ? `<img data-momento="${momento}" alt="Foto ${ETIQUETAS[momento]} de la actividad ${SGML.escaparHTML(actividad.id)}" loading="lazy">`
                : `<span class="error-foto">Evidencia no registrada</span>`}
            </section>`).join("")}
        </div>
        <form class="revision" data-id="${SGML.escaparHTML(actividad.id)}">
          <label class="observacion">Observación (obligatoria si rechazas)
            <textarea name="observacion" rows="2" maxlength="300"></textarea>
          </label>
          <button type="submit" name="resultado" value="ACEPTADA">Aceptar</button>
          <button class="rechazar" type="submit" name="resultado" value="RECHAZADA">Rechazar</button>
        </form>`;
      lista.append(tarjeta);

      tarjeta.querySelectorAll("img[data-momento]").forEach((imagen) => {
        const momento = imagen.dataset.momento;
        const ruta = `/api/jornada/actividades/${actividad.id}/evidencias/${momento}`;
        SGML.obtenerImagen(ruta).then((url) => {
          urlsImagenes.add(url);
          imagen.src = url;
        }).catch((error) => {
          imagen.replaceWith(Object.assign(document.createElement("span"), {
            className: "error-foto",
            textContent: error.message,
          }));
        });
      });
    });
  }

  async function cargarPendientes() {
    const boton = document.getElementById("actualizar");
    const estado = document.getElementById("actualizado");
    boton.disabled = true;
    estado.textContent = "Consultando…";
    try {
      const query = new URLSearchParams({ fecha: fecha.value || SGML.fechaLocal() });
      const pendientes = await SGML.solicitar(`/api/jornada/revisiones?${query}`);
      renderizar(pendientes);
      estado.textContent = `Actualizado ${new Date().toLocaleTimeString()}`;
    } catch (error) {
      mostrarMensaje(`No se pudieron cargar las actividades: ${error.message}`, "error");
      estado.textContent = "No se pudo actualizar";
    } finally {
      boton.disabled = false;
    }
  }

  async function revisar(evento) {
    evento.preventDefault();
    const formulario = evento.target.closest("form.revision");
    if (!formulario) return;
    const resultado = evento.submitter?.value;
    const observacion = new FormData(formulario).get("observacion").trim();
    if (resultado === "RECHAZADA" && !observacion) {
      mostrarMensaje("Escribe una observación para rechazar la actividad.", "error");
      formulario.elements.observacion.focus();
      return;
    }

    const botones = Array.from(formulario.querySelectorAll("button"));
    botones.forEach((boton) => { boton.disabled = true; });
    try {
      await SGML.solicitar(`/api/jornada/actividades/${formulario.dataset.id}/revision`, {
        method: "PATCH",
        body: JSON.stringify({
          resultado,
          observacion: observacion || null,
        }),
      });
      mostrarMensaje(resultado === "ACEPTADA"
        ? "Actividad aceptada correctamente."
        : "Actividad rechazada. Se creó una tarea de corrección para el Operario.");
      await cargarPendientes();
    } catch (error) {
      mostrarMensaje(`No se pudo guardar la revisión: ${error.message}`, "error");
      botones.forEach((boton) => { boton.disabled = false; });
    }
  }

  document.getElementById("actualizar").addEventListener("click", cargarPendientes);
  document.getElementById("cerrar-sesion").addEventListener("click", SGML.cerrarSesion);
  fecha.addEventListener("change", cargarPendientes);
  lista.addEventListener("submit", revisar);
  void cargarPendientes();

  window.setInterval(() => {
    if (!document.hidden && !document.querySelector("form.revision textarea:focus")) {
      void cargarPendientes();
    }
  }, 30000);
}
