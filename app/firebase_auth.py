"""
firebase_auth.py
────────────────
Dependencia FastAPI que verifica el Firebase ID Token enviado
en el header `Authorization: Bearer <token>`.

Uso en un endpoint:
    from app.firebase_auth import get_current_user

    @app.post("/api/extract")
    async def extract(user=Depends(get_current_user), file: UploadFile = File(...)):
        # user.uid, user.email disponibles aquí
        ...
"""

import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import auth as firebase_auth

logger = logging.getLogger(__name__)

# Esquema de seguridad Bearer para la UI de Swagger
_bearer_scheme = HTTPBearer(auto_error=False)


class FirebaseUser:
    """Representa al usuario autenticado una vez verificado el token."""
    def __init__(self, uid: str, email: Optional[str] = None, name: Optional[str] = None):
        self.uid = uid
        self.email = email
        self.name = name

    def __repr__(self):
        return f"<FirebaseUser uid={self.uid} email={self.email}>"


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> FirebaseUser:
    """
    Dependencia FastAPI que:
    1. Lee el header Authorization: Bearer <token>
    2. Verifica la firma del token con Firebase Admin SDK
    3. Retorna un FirebaseUser con uid y email

    Lanza HTTPException 401 si:
    - No hay header Authorization
    - El token está expirado
    - El token es inválido o de otro proyecto
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación. Incluye el token de Firebase en el header Authorization.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        decoded = firebase_auth.verify_id_token(token)
        return FirebaseUser(
            uid=decoded["uid"],
            email=decoded.get("email"),
            name=decoded.get("name"),
        )
    except firebase_admin.auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token de Firebase ha expirado. Vuelve a iniciar sesión.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except firebase_admin.auth.InvalidIdTokenError as e:
        logger.warning(f"Token inválido recibido: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de Firebase inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Error inesperado verificando token Firebase: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se pudo verificar la autenticación.",
            headers={"WWW-Authenticate": "Bearer"},
        )
