"""Errores de negocio compartidos.

DRY: todos los módulos lanzan estas excepciones y un único manejador
(app/main.py) las traduce a respuestas HTTP.
"""


class ErrorDeNegocio(Exception):
    """Una regla de negocio fue violada (HTTP 422)."""


class NoEncontrado(Exception):
    """El recurso solicitado no existe (HTTP 404)."""


class Conflicto(Exception):
    """El recurso ya existe o choca con otro (HTTP 409)."""
