"use strict";

const ROLES_ADMINISTRATIVOS = new Set(["ADMINISTRADOR", "ADMINISTRATIVO"]);
const ETIQUETAS_ROL = {
  ADMINISTRADOR: "Administrador",
  ADMINISTRATIVO: "Administrativo",
};
const rol = SGMLAuth.obtener("sgml-rol");
const mensaje = document.getElementById("mensaje");
const filasOperarios = document.getElementById("filas-operarios");
const formularioRegistro = document.getElementById("form-registro");
const formularioContacto = document.getElementById("form-contacto");
const dialogoContacto = document.getElementById("dialogo-contacto");
const listaFormacion = document.getElementById("lista-formacion");
const listaExperiencia = document.getElementById("lista-experiencia");
const dialogoPerfil = document.getElementById("dialogo-perfil");
let operarios = [];
let operarioEnEdicion = null;
let secuenciaFila = 0;

function mostrarMensaje(texto, tipo = "ok") {
  mensaje.textContent = texto;
  mensaje.className = `mensaje ${tipo}`;
  mensaje.hidden = false;
}

function limpiarMensaje() {
  mensaje.textContent = "";
  mensaje.hidden = true;
}

function agregarFila(contenedor, plantillaId, prefijo) {
  const fila = document.getElementById(plantillaId).content.firstElementChild.cloneNode(true);
  const numero = ++secuenciaFila;
  fila.querySelectorAll("[data-campo]").forEach((entrada) => {
    const id = `${prefijo}-${numero}-${entrada.dataset.campo}`;
    entrada.id = id;
    entrada.parentElement.querySelector("label").htmlFor = id;
  });
  fila.querySelector("[data-quitar]").addEventListener("click", () => fila.remove());
  contenedor.append(fila);
}

function recopilarFilas(contenedor, camposNumericos) {
  return Array.from(contenedor.children, (fila) => {
    const registro = {};
    fila.querySelectorAll("[data-campo]").forEach((entrada) => {
      const valor = entrada.value.trim();
      registro[entrada.dataset.campo] = camposNumericos.has(entrada.dataset.campo)
        ? valor === "" ? null : Number(valor)
        : valor;
    });
    return registro;
  });
}

function mostrarPerfil(id) {
  const operario = operarios.find((item) => item.id === id);
  if (!operario) {
    mostrarMensaje("No se encontró el operario seleccionado.", "error");
    return;
  }
  document.getElementById("nombre-perfil").textContent =
    `${operario.nombre_completo} · Documento ${operario.documento}`;
  const formacion = operario.formacion.length
    ? `<ul>${operario.formacion.map((item) => `
        <li><strong>${escaparHTML(item.titulo)}</strong> — ${escaparHTML(item.nivel)},
          ${escaparHTML(item.institucion)}          ${item.anio_fin !== null && item.anio_fin !== undefined
            ? ` (${escaparHTML(item.anio_fin)})`
            : ""}</li>`).join("")}</ul>`
    : "<p>Sin formación registrada.</p>";
  const experiencia = operario.experiencia.length
    ? `<ul>${operario.experiencia.map((item) => `
        <li><strong>${escaparHTML(item.cargo)}</strong> — ${escaparHTML(item.empresa)},
          ${escaparHTML(item.meses)} meses</li>`).join("")}</ul>`
    : "<p>Sin experiencia registrada.</p>";
  document.getElementById("detalle-perfil").innerHTML = `
    <p><strong>Especialidades:</strong> ${operario.especialidades
      .map(escaparHTML).join(", ")}</p>
    <p><strong>Experiencia total:</strong> ${escaparHTML(operario.anios_experiencia)} años</p>
    <h3>Formación</h3>${formacion}
    <h3>Experiencia laboral</h3>${experiencia}`;
  dialogoPerfil.showModal();
}

function escaparHTML(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (caracter) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[caracter]);
}

async function solicitar(ruta, opciones = {}) {
  const headers = new Headers(opciones.headers || {});
  if (opciones.body && !(opciones.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const respuesta = await SGMLAuth.fetchAutenticado(ruta, { ...opciones, headers });
  const tipoContenido = respuesta.headers.get("content-type") || "";
  const resultado = tipoContenido.includes("application/json")
    ? await respuesta.json()
    : null;
  if (!respuesta.ok) {
    const detalle = Array.isArray(resultado?.detail)
      ? resultado.detail.map((error) => error.msg).join("; ")
      : typeof resultado?.detail === "string"
        ? resultado.detail
        : `El servidor respondió ${respuesta.status}.`;
    throw new Error(detalle);
  }
  return resultado;
}

function dibujarOperarios() {
  filasOperarios.innerHTML = operarios.map((operario) => {
    const activo = operario.estado === "ACTIVO";
    const accionEstado = activo ? "inactivar" : "activar";
    const claseEstado = activo ? "activo" : "inactivo";
    const textoEstado = activo ? "Activo" : "Inactivo";
    return `<tr>
      <td>${escaparHTML(operario.id)}</td>
      <td>${escaparHTML(operario.nombre_completo)}</td>
      <td>${escaparHTML(operario.documento)}</td>
      <td>${escaparHTML(operario.telefono)}<br>${escaparHTML(operario.correo_institucional)}</td>
      <td>${escaparHTML(operario.fecha_ingreso)}</td>
      <td>${escaparHTML(operario.anios_experiencia)} años</td>
      <td><span class="estado ${claseEstado}">${textoEstado}</span></td>
      <td><div class="acciones-fila">
        <button class="secundario" type="button" data-accion="perfil"
          data-id="${escaparHTML(operario.id)}">Ver hoja de vida</button>
        <button class="secundario" type="button" data-accion="editar"
          data-id="${escaparHTML(operario.id)}">Editar contacto</button>
        <button class="${activo ? "peligro" : "secundario"}" type="button"
          data-accion="${accionEstado}" data-id="${escaparHTML(operario.id)}">
          ${activo ? "Inactivar" : "Activar"}
        </button>
      </div></td>
    </tr>`;
  }).join("");

  document.getElementById("total-operarios").textContent =
    `${operarios.length} ${operarios.length === 1 ? "operario" : "operarios"}`;
  document.getElementById("sin-operarios").hidden = operarios.length > 0;
}

async function cargarOperarios() {
  const boton = document.getElementById("actualizar-listado");
  boton.disabled = true;
  try {
    operarios = await solicitar("/api/operarios");
    dibujarOperarios();
  } catch (error) {
    mostrarMensaje(`No se pudo cargar el listado: ${error.message}`, "error");
  } finally {
    boton.disabled = false;
  }
}

async function registrarOperario(evento) {
  evento.preventDefault();
  limpiarMensaje();
  const especialidades = Array.from(
    formularioRegistro.querySelectorAll('input[name="especialidades"]:checked'),
    (control) => control.value,
  );
  if (!especialidades.length) {
    mostrarMensaje("Selecciona al menos una especialidad.", "error");
    return;
  }

  const datos = new FormData(formularioRegistro);
  const operario = {
    documento: datos.get("documento").trim(),
    nombres: datos.get("nombres").trim(),
    apellidos: datos.get("apellidos").trim(),
    telefono: datos.get("telefono").trim(),
    correo_institucional: datos.get("correo_institucional").trim(),
    fecha_ingreso: datos.get("fecha_ingreso"),
    especialidades,
    formacion: recopilarFilas(listaFormacion, new Set(["anio_fin"])),
    experiencia: recopilarFilas(listaExperiencia, new Set(["meses"])),
  };
  const boton = document.getElementById("registrar");
  boton.disabled = true;
  try {
    await solicitar("/api/operarios", {
      method: "POST",
      body: JSON.stringify(operario),
    });
    listaFormacion.replaceChildren();
    listaExperiencia.replaceChildren();
    formularioRegistro.reset();
    mostrarMensaje("Operario registrado correctamente.");
    await cargarOperarios();
  } catch (error) {
    mostrarMensaje(`No se pudo registrar el operario: ${error.message}`, "error");
  } finally {
    boton.disabled = false;
  }
}

function abrirEdicion(id) {
  const operario = operarios.find((item) => item.id === id);
  if (!operario) {
    mostrarMensaje("No se encontró el operario seleccionado.", "error");
    return;
  }
  operarioEnEdicion = operario.id;
  document.getElementById("nombre-contacto").textContent = operario.nombre_completo;
  document.getElementById("telefono-contacto").value = operario.telefono;
  document.getElementById("correo-contacto").value = operario.correo_institucional;
  dialogoContacto.showModal();
}

async function guardarContacto(evento) {
  evento.preventDefault();
  if (operarioEnEdicion === null) return;
  const datos = new FormData(formularioContacto);
  const boton = formularioContacto.querySelector('button[type="submit"]');
  boton.disabled = true;
  try {
    await solicitar(`/api/operarios/${operarioEnEdicion}/contacto`, {
      method: "PUT",
      body: JSON.stringify({
        telefono: datos.get("telefono").trim(),
        correo_institucional: datos.get("correo_institucional").trim(),
      }),
    });
    dialogoContacto.close();
    mostrarMensaje("Datos de contacto actualizados.");
    await cargarOperarios();
  } catch (error) {
    mostrarMensaje(`No se pudo actualizar el contacto: ${error.message}`, "error");
  } finally {
    boton.disabled = false;
  }
}

async function cambiarEstado(id, activo) {
  const operario = operarios.find((item) => item.id === id);
  if (!operario) {
    mostrarMensaje("No se encontró el operario seleccionado.", "error");
    return;
  }
  const accion = activo ? "activar" : "inactivar";
  if (!window.confirm(`¿Confirmas ${accion} a ${operario.nombre_completo}?`)) return;
  try {
    await solicitar(`/api/operarios/${id}/estado`, {
      method: "PATCH",
      body: JSON.stringify({ activo }),
    });
    mostrarMensaje(`Operario ${activo ? "activado" : "inactivado"} correctamente.`);
    await cargarOperarios();
  } catch (error) {
    mostrarMensaje(`No se pudo cambiar el estado: ${error.message}`, "error");
  }
}

const accionesOperario = {
  perfil: (id) => mostrarPerfil(id),
  editar: (id) => abrirEdicion(id),
  activar: (id) => cambiarEstado(id, true),
  inactivar: (id) => cambiarEstado(id, false),
};

function cerrarSesion() {
  SGMLAuth.limpiar();
  window.location.assign("/app/login.html");
}

function iniciarBackoffice() {
  if (!SGMLAuth.tieneSesion() || !ROLES_ADMINISTRATIVOS.has(rol)) {
    document.querySelector("main").innerHTML =
      '<section class="tarjeta"><h2>Acceso no disponible</h2>' +
      '<p>Esta vista es para Administradores y Administrativos. Inicia sesión con un rol autorizado.</p>' +
      '<a href="/app/login.html">Volver al inicio de sesión</a></section>';
    return;
  }
  document.getElementById("usuario-rol").textContent =
    ETIQUETAS_ROL[rol] || "Gestión de operarios";
  document.getElementById("enlace-programacion").hidden = rol !== "ADMINISTRADOR";
  document.getElementById("actualizar-listado")
    .addEventListener("click", cargarOperarios);
  document.getElementById("cerrar-sesion").addEventListener("click", cerrarSesion);
  formularioRegistro.addEventListener("submit", registrarOperario);
  document.getElementById("agregar-formacion").addEventListener("click", () =>
    agregarFila(listaFormacion, "plantilla-formacion", "formacion"));
  document.getElementById("agregar-experiencia").addEventListener("click", () =>
    agregarFila(listaExperiencia, "plantilla-experiencia", "experiencia"));
  formularioContacto.addEventListener("submit", guardarContacto);
  ["correo", "correo-contacto"].forEach((id) => {
    document.getElementById(id).addEventListener("input", (evento) => {
      evento.currentTarget.value = evento.currentTarget.value.toLowerCase();
    });
  });
  document.getElementById("cancelar-contacto").addEventListener("click", () => {
    dialogoContacto.close();
  });
  document.getElementById("cerrar-perfil").addEventListener("click", () => {
    dialogoPerfil.close();
  });
  dialogoContacto.addEventListener("close", () => {
    operarioEnEdicion = null;
    formularioContacto.reset();
  });
  filasOperarios.addEventListener("click", (evento) => {
    const boton = evento.target.closest("button[data-accion]");
    if (!boton) return;
    const ejecutar = accionesOperario[boton.dataset.accion];
    if (ejecutar) void ejecutar(Number(boton.dataset.id));
  });
  void cargarOperarios();
}

iniciarBackoffice();
