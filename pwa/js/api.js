"use strict";

window.SGML = (() => {
  const TOKEN_KEY = "sgml-access-token";
  const ROLE_KEY = "sgml-rol";

  function rolActual() {
    return localStorage.getItem(ROLE_KEY);
  }

  function exigirRol(roles) {
    if (localStorage.getItem(TOKEN_KEY) && roles.includes(rolActual())) return true;
    window.location.replace("/app/login.html");
    return false;
  }

  function cerrarSesion() {
    ["sgml-access-token", "sgml-refresh-token", ROLE_KEY].forEach((clave) =>
      localStorage.removeItem(clave));
    window.location.assign("/app/login.html");
  }

  async function solicitar(ruta, opciones = {}) {
    const headers = new Headers(opciones.headers || {});
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (opciones.body && !(opciones.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    const respuesta = await fetch(ruta, { ...opciones, headers });
    const tipoContenido = respuesta.headers.get("content-type") || "";
    const cuerpo = tipoContenido.includes("application/json")
      ? await respuesta.json()
      : null;
    if (respuesta.status === 401) {
      cerrarSesion();
      throw new Error("La sesión expiró; inicia sesión nuevamente.");
    }
    if (!respuesta.ok) {
      const detalle = Array.isArray(cuerpo?.detail)
        ? cuerpo.detail.map((error) => error.msg).join("; ")
        : typeof cuerpo?.detail === "string"
          ? cuerpo.detail
          : `El servidor respondió ${respuesta.status}.`;
      throw new Error(detalle);
    }
    return cuerpo;
  }

  async function obtenerImagen(ruta) {
    const respuesta = await fetch(ruta, {
      headers: { Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY)}` },
    });
    if (respuesta.status === 401) {
      cerrarSesion();
      throw new Error("La sesión expiró; inicia sesión nuevamente.");
    }
    if (!respuesta.ok) {
      throw new Error(`No se pudo cargar una evidencia (${respuesta.status}).`);
    }
    return URL.createObjectURL(await respuesta.blob());
  }

  function fechaLocal() {
    const ahora = new Date();
    const dosDigitos = (valor) => String(valor).padStart(2, "0");
    return `${ahora.getFullYear()}-${dosDigitos(ahora.getMonth() + 1)}-${dosDigitos(ahora.getDate())}`;
  }

  function escaparHTML(valor) {
    return String(valor ?? "").replace(/[&<>"']/g, (caracter) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[caracter]);
  }

  return { exigirRol, rolActual, cerrarSesion, solicitar, obtenerImagen, fechaLocal, escaparHTML };
})();
