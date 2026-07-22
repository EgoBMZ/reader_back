import logging
from typing import Dict, Any, Optional
from firebase_admin import firestore
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def get_db():
    """Obtiene el cliente de Firestore."""
    return firestore.client()

def init_db():
    """Firestore no requiere inicialización de tablas. No-op."""
    logger.info("Base de datos conectada (Firestore).")

def save_user_progress(user_id: str, book_id: str, current_element_id: int, char_offset: int = 0) -> bool:
    """
    Guarda o actualiza el progreso de lectura del usuario (UPSERT) en Firestore.
    """
    try:
        db = get_db()
        doc_ref = db.collection('users').document(user_id).collection('progress').document(book_id)
        doc_ref.set({
            "current_element_id": current_element_id,
            "char_offset": char_offset,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        return True
    except Exception as e:
        logger.error(f"Error al guardar progreso de lectura en Firestore para {user_id} en libro {book_id}: {e}")
        return False

def get_user_progress(user_id: str, book_id: str) -> Optional[Dict[str, Any]]:
    """
    Recupera el progreso de lectura guardado de un usuario en un libro determinado desde Firestore.
    """
    try:
        db = get_db()
        doc_ref = db.collection('users').document(user_id).collection('progress').document(book_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            return {
                "user_id": user_id,
                "book_id": book_id,
                "current_element_id": data.get("current_element_id"),
                "char_offset": data.get("char_offset", 0),
                "updated_at": data.get("updated_at")
            }
        return None
    except Exception as e:
        logger.error(f"Error al obtener progreso de lectura en Firestore para {user_id} en libro {book_id}: {e}")
        return None
