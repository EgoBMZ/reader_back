import os
import sqlite3
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Define DB path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reader.db")

def get_db_connection():
    """Establece una conexión con la base de datos SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite acceder a las columnas por nombre
    return conn

def init_db():
    """Inicializa la base de datos y crea las tablas si no existen."""
    logger.info(f"Inicializando base de datos en: {DB_PATH}")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                user_id TEXT NOT NULL,
                book_id TEXT NOT NULL,
                current_element_id INTEGER NOT NULL,
                char_offset INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, book_id)
            )
        """)
        conn.commit()
        logger.info("Base de datos e inicialización de tablas completadas.")
    except Exception as e:
        logger.error(f"Error al inicializar la base de datos: {e}")
        raise e
    finally:
        conn.close()

def save_user_progress(user_id: str, book_id: str, current_element_id: int, char_offset: int = 0) -> bool:
    """
    Guarda o actualiza el progreso de lectura del usuario (UPSERT).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_progress (user_id, book_id, current_element_id, char_offset, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, book_id) DO UPDATE SET
                current_element_id = excluded.current_element_id,
                char_offset = excluded.char_offset,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, book_id, current_element_id, char_offset))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error al guardar progreso de lectura para {user_id} en libro {book_id}: {e}")
        return False
    finally:
        conn.close()

def get_user_progress(user_id: str, book_id: str) -> Optional[Dict[str, Any]]:
    """
    Recupera el progreso de lectura guardado de un usuario en un libro determinado.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT current_element_id, char_offset, updated_at 
            FROM user_progress 
            WHERE user_id = ? AND book_id = ?
        """, (user_id, book_id))
        row = cursor.fetchone()
        if row:
            return {
                "user_id": user_id,
                "book_id": book_id,
                "current_element_id": row["current_element_id"],
                "char_offset": row["char_offset"],
                "updated_at": row["updated_at"]
            }
        return None
    except Exception as e:
        logger.error(f"Error al obtener progreso de lectura para {user_id} en libro {book_id}: {e}")
        return None
    finally:
        conn.close()
