import os
import shutil
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage

from app.services.pdf_parser import PDFParserService
from app.firebase_auth import get_current_user, FirebaseUser

# ─── Config ───────────────────────────────────────────────────────────────────
# Carga variables desde backend/.env
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "reader-egobmz")
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", f"{FIREBASE_PROJECT_ID}.appspot.com")
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3001,http://localhost:3000,*").split(",")
    if o.strip()
]

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Directorios ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

# ─── Firebase Admin SDK ───────────────────────────────────────────────────────
def _init_firebase():
    """
    Inicializa Firebase Admin SDK.
    """
    if firebase_admin._apps:
        return  # ya inicializado (útil en hot-reload)

    # 1. Si hay JSON directo en env (útil para Render)
    cred_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
    sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    options = {
        "projectId": FIREBASE_PROJECT_ID,
        "storageBucket": FIREBASE_STORAGE_BUCKET
    }

    if cred_json_str:
        try:
            cred_dict = json.loads(cred_json_str)
            cred = credentials.Certificate(cred_dict)
            logger.info("Firebase Admin: usando credenciales desde FIREBASE_CREDENTIALS_JSON")
        except json.JSONDecodeError:
            logger.error("El contenido de FIREBASE_CREDENTIALS_JSON no es un JSON válido.")
            cred = None
    elif sa_path and Path(sa_path).exists():
        cred = credentials.Certificate(sa_path)
        logger.info(f"Firebase Admin: usando service account desde {sa_path}")
    else:
        cred = credentials.ApplicationDefault() if os.getenv("GOOGLE_CLOUD_PROJECT") else None
        logger.info(
            f"Firebase Admin: inicializando sin credenciales explícitas "
            "(solo válido si la máquina ya está autenticada con GCP/Firebase)"
        )

    try:
        if cred:
            firebase_admin.initialize_app(cred, options)
        else:
            firebase_admin.initialize_app(options=options)
    except ValueError:
        pass  # app ya existe


_init_firebase()

# ─── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Lexis PDF Processing API",
    description=(
        "Procesa archivos PDF y devuelve su contenido como JSON estructurado. "
        "Todos los endpoints protegidos requieren un Firebase ID Token válido."
    ),
    version="2.0.0",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# ─── Servicios ─────────────────────────────────────────────────────────────────
# Seguimos usando STATIC_DIR y UPLOAD_DIR localmente de forma temporal, 
# pero ya no servimos los archivos estáticos desde FastAPI.
parser_service = PDFParserService(static_dir=STATIC_DIR, upload_dir=UPLOAD_DIR)


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS PÚBLICOS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["General"])
async def root():
    return {
        "status": "online",
        "version": "2.0.0",
        "message": "Lexis PDF Processing API — ver /docs para la documentación.",
    }


@app.get("/health", tags=["General"])
async def health():
    """Health check: verifica que el servidor y Java estén disponibles."""
    java_installed = shutil.which("java") is not None
    return {
        "status": "healthy",
        "firebase_project": FIREBASE_PROJECT_ID,
        "java_installed": java_installed,
        "java_path": shutil.which("java") if java_installed else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS PROTEGIDOS (requieren Firebase ID Token)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/extract", tags=["PDF Processing"])
async def extract_pdf(
    file: UploadFile = File(...),
    user: FirebaseUser = Depends(get_current_user),
):
    """
    Sube un PDF para procesar su estructura.

    **Requiere autenticación**: incluye el Firebase ID Token en el header:
    ```
    Authorization: Bearer <token>
    ```

    Retorna un JSON estructurado con el contenido del libro (elementos, jerarquía, etc.)
    listo para guardarse en Firestore.
    """
    # 1. Validar extensión
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se aceptan archivos PDF.",
        )

    logger.info(f"[extract] Usuario {user.uid} ({user.email}) subiendo '{file.filename}'")

    # 2. Guardar temporalmente
    safe_filename = file.filename.replace(" ", "_")
    temp_path = os.path.join(UPLOAD_DIR, f"temp_{user.uid}_{safe_filename}")
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"[extract] Error guardando archivo temporal: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo guardar el archivo: {e}",
        )

    # 3. Parsear PDF
    from fastapi.concurrency import run_in_threadpool
    try:
        result = await run_in_threadpool(parser_service.parse, temp_path)
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Error desconocido durante el procesamiento del PDF."),
            )
        logger.info(f"[extract] PDF procesado exitosamente para usuario {user.uid}")
        return JSONResponse(content=result)

    finally:
        # 4. Limpiar archivo temporal
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"[extract] No se pudo borrar el archivo temporal {temp_path}: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
