"use strict";

const ROLES_ADMINISTRATIVOS = new Set(["ADMINISTRADOR", "ADMINISTRATIVO"]);
const ETIQUETAS_ROL = {
  ADMINISTRADOR: "Administrador",
  ADMINISTRATIVO: "Administrativo",
};
const token = localStorage.getItem("sgml-access-token");
const rol = localStorage.getItem("sgml-rol");
const mensaje = document.getElementById("mensaje");
const filasOperarios = document.getElementById("filas-operarios");
const formularioRegistro = document.getElementById("form-registro");
const formularioContacto = document.getElementById("form-contacto");
const dialogoContacto = document.getElementById("dialogo-contacto");
let operarios = [];
let operarioEnEdicion = null;

function mostrarMensaje(texto, tipo = "ok") {
  mensaje.textContent = texto;
  mensaje.className = `mensaje ${tipo}`;
  mensaje.hidden = false;
}

function limpiarMensaje() {
  mensaje.textContent = "";
  mensaje.hidden = true;
}

function escaparHTML(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (caracter) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[caracter]);
}

async function solicitar(ruta, opciones = {}) {
  const headers = new Headers(opciones.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  if (opciones.body && !(opciones.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const respuesta = await fetch(ruta, { ...opciones, headers });
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
      <td><span class="estado ${claseEstado}">${textoEstado}</span></td>
      <td><div class="acciones-fila">
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
    formacion: [],
    experiencia: [],
  };
  const boton = document.getElementById("registrar");
  boton.disabled = true;
  try {
    await solicitar("/api/operarios", {
      method: "POST",
      body: JSON.stringify(operario),
    });
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
  editar: (id) => abrirEdicion(id),
  activar: (id) => cambiarEstado(id, true),
  inactivar: (id) => cambiarEstado(id, false),
};

function cerrarSesion() {
  ["sgml-access-token", "sgml-refresh-token", "sgml-rol"].forEach((clave) =>
    localStorage.removeItem(clave));
  window.location.assign("/app/login.html");
}

function iniciarBackoffice() {
  if (!token || !ROLES_ADMINISTRATIVOS.has(rol)) {
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
  formularioContacto.addEventListener("submit", guardarContacto);
  ["correo", "correo-contacto"].forEach((id) => {
    document.getElementById(id).addEventListener("input", (evento) => {
      evento.currentTarget.value = evento.currentTarget.value.toLowerCase();
    });
  });
  document.getElementById("cancelar-contacto").addEventListener("click", () => {
    dialogoContacto.close();
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
