"use strict";

const DESTINOS_POR_ROL = {
  ADMINISTRADOR: "/app/programacion.html",
  ADMINISTRATIVO: "/app/dashboard.html",
  SUPERVISOR: "/app/supervisor.html",
  OPERARIO: "/app/",
};

const formulario = document.getElementById("form-login");
const boton = document.getElementById("enviar");
const mensaje = document.getElementById("mensaje");

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  mensaje.textContent = "";
  boton.disabled = true;

  const datos = new URLSearchParams(new FormData(formulario));
  try {
    const respuesta = await fetch("/api/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: datos,
    });
    if (!respuesta.ok) {
      mensaje.textContent = respuesta.status === 401
        ? "Usuario o contraseña incorrectos."
        : "No fue posible iniciar sesión. Intenta de nuevo.";
      return;
    }

    const sesion = await respuesta.json();
    const destino = DESTINOS_POR_ROL[sesion.rol];
    if (!destino || !sesion.access_token || !sesion.refresh_token) {
      mensaje.textContent = "La respuesta de autenticación no es válida.";
      return;
    }
    if (sesion.rol === "OPERARIO" && !sesion.operario_id) {
      mensaje.textContent = "Esta cuenta no está vinculada a un operario.";
      return;
    }

    localStorage.setItem("sgml-access-token", sesion.access_token);
    localStorage.setItem("sgml-refresh-token", sesion.refresh_token);
    localStorage.setItem("sgml-rol", sesion.rol);
    localStorage.setItem("sgml-nombre-usuario", sesion.nombre_usuario);
    if (sesion.rol === "OPERARIO") {
      localStorage.setItem("sgml-operario-id", String(sesion.operario_id));
    } else {
      localStorage.removeItem("sgml-operario-id");
    }
    window.location.assign(destino);
  } catch {
    mensaje.textContent = "No hay conexión con el servidor. Conéctate para iniciar sesión.";
  } finally {
    boton.disabled = false;
  }
});
