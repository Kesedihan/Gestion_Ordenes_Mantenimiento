"use strict";

window.SGMLAuth = (() => {
  const CLAVES = [
    "sgml-access-token",
    "sgml-refresh-token",
    "sgml-rol",
    "sgml-operario-id",
    "sgml-nombre-usuario",
  ];
  const RECORDAR = "sgml-recordarme";

  if (
    localStorage.getItem("sgml-access-token")
    && localStorage.getItem(RECORDAR) === null
    && !sessionStorage.getItem("sgml-access-token")
  ) {
    localStorage.setItem(RECORDAR, "1");
  }

  function almacenamiento() {
    return localStorage.getItem(RECORDAR) === "1" ? localStorage : sessionStorage;
  }

  function obtener(clave) {
    return almacenamiento().getItem(clave);
  }

  function guardar(sesion, recordar) {
    limpiar();
    const destino = recordar ? localStorage : sessionStorage;
    destino.setItem("sgml-access-token", sesion.access_token);
    destino.setItem("sgml-refresh-token", sesion.refresh_token);
    destino.setItem("sgml-rol", sesion.rol);
    destino.setItem("sgml-nombre-usuario", sesion.nombre_usuario);
    if (sesion.operario_id) {
      destino.setItem("sgml-operario-id", String(sesion.operario_id));
    }
    if (recordar) localStorage.setItem(RECORDAR, "1");
  }

  function guardarAccessToken(token) {
    almacenamiento().setItem("sgml-access-token", token);
  }

  function limpiar() {
    CLAVES.forEach((clave) => {
      localStorage.removeItem(clave);
      sessionStorage.removeItem(clave);
    });
    localStorage.removeItem(RECORDAR);
  }

  function tieneSesion() {
    return Boolean(obtener("sgml-access-token") && obtener("sgml-rol"));
  }

  async function fetchAutenticado(ruta, opciones = {}) {
    const ejecutar = () => {
      const headers = new Headers(opciones.headers || {});
      const token = obtener("sgml-access-token");
      if (token) headers.set("Authorization", `Bearer ${token}`);
      return fetch(ruta, { ...opciones, headers });
    };

    const respuesta = await ejecutar();
    if (respuesta.status !== 401) return respuesta;

    const refreshToken = obtener("sgml-refresh-token");
    if (!refreshToken) return respuesta;

    const renovacion = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (renovacion.status === 401) {
      limpiar();
      return respuesta;
    }
    if (!renovacion.ok) {
      throw new Error("No se pudo renovar la sesión. Intenta de nuevo cuando haya conexión.");
    }

    const credenciales = await renovacion.json();
    if (!credenciales.access_token) {
      limpiar();
      throw new Error("El servidor devolvió una respuesta de renovación inválida.");
    }
    guardarAccessToken(credenciales.access_token);

    const reintento = await ejecutar();
    if (reintento.status === 401) limpiar();
    return reintento;
  }

  return {
    obtener,
    guardar,
    limpiar,
    tieneSesion,
    fetchAutenticado,
    recordar: () => localStorage.getItem(RECORDAR) === "1",
  };
})();
