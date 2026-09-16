"""Initialisation idempotente de la base SQLite du projet."""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def apply_schema(connection: sqlite3.Connection) -> None:
    """Applique le schéma sans modifier ni supprimer les snapshots existants."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def create_database(database_path: str | Path) -> None:
    """Crée la base si nécessaire et applique le schéma de façon idempotente."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        apply_schema(connection)
