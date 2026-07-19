import os
import shutil
import logging
import json
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from app.services.pdf_parser import PDFParserService
from app.services.pdf_reconstructor import PDFReconstructorService
from app.database import init_db, save_user_progress, get_user_progress
from app.services.toc import TOCService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

# Initialize FastAPI
app = FastAPI(
    title="OpenDataLoader PDF Structuring API",
    description="Backend service to parse PDF books into structured JSON layout maps and extract embedded images.",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    init_db()

# Configure CORS for Web/Mobile clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize PDF Parser Service
# This will also ensure STATIC_DIR and UPLOAD_DIR exist
parser_service = PDFParserService(static_dir=STATIC_DIR, upload_dir=UPLOAD_DIR)
reconstructor_service = PDFReconstructorService(static_dir=STATIC_DIR, upload_dir=UPLOAD_DIR)

class ReconstructRequest(BaseModel):
    document: list
    task_id: str

class ProgressSaveRequest(BaseModel):
    user_id: str
    book_id: str
    current_element_id: int
    char_offset: int = 0

# Mount the static directory to serve extracted images
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", tags=["General"])
async def root():
    return {
        "status": "online",
        "message": "Welcome to OpenDataLoader PDF Structuring API. Check /docs for interactive Swagger UI."
    }

@app.get("/health", tags=["General"])
async def health():
    # Basic check to see if Java is available in PATH
    java_installed = shutil.which("java") is not None
    return {
        "status": "healthy",
        "java_installed": java_installed,
        "java_path": shutil.which("java") if java_installed else None
    }

@app.post("/api/extract", tags=["PDF Processing"])
async def extract_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF file to analyze its layout, extract text hierarchy, tables, and images.
    Returns a structured JSON payload with bounding boxes and links to extracted images.
    """
    # 1. Validate file extension
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only PDF files are supported."
        )
    
    # 2. Save uploaded file temporarily
    temp_filename = f"temp_{file.filename}"
    temp_filepath = os.path.join(UPLOAD_DIR, temp_filename)
    
    logger.info(f"Saving uploaded file to temporary path: {temp_filepath}")
    try:
        with open(temp_filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )
        
    # 3. Parse the PDF using OpenDataLoader
    try:
        result = parser_service.parse(temp_filepath)
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "An unknown error occurred during PDF parsing.")
            )
        return JSONResponse(content=result)
    
    finally:
        # 4. Clean up temporary uploaded file
        if os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
                logger.info(f"Cleaned up temporary file: {temp_filepath}")
            except Exception as e:
                logger.error(f"Failed to delete temporary file {temp_filepath}: {str(e)}")

@app.post("/api/reconstruct", tags=["PDF Processing"])
async def reconstruct_pdf(payload: ReconstructRequest):
    """
    Rebuilds a new PDF document from the structured elements and returns it for download.
    """
    try:
        pdf_path = reconstructor_service.reconstruct(payload.document, payload.task_id)
        if not os.path.exists(pdf_path):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Reconstructed PDF file was not found on disk."
            )
        return FileResponse(
            path=pdf_path,
            media_type="application/pdf",
            filename=f"reconstructed_{payload.task_id}.pdf"
        )
    except Exception as e:
        logger.exception("Error occurred during PDF reconstruction")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post("/api/progress", tags=["Reading Progress"])
async def save_progress(payload: ProgressSaveRequest):
    """
    Guarda o actualiza el progreso de lectura (narrador) del usuario en un libro.
    """
    success = save_user_progress(
        user_id=payload.user_id,
        book_id=payload.book_id,
        current_element_id=payload.current_element_id,
        char_offset=payload.char_offset
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save reading progress."
        )
    return {"status": "success", "message": "Reading progress updated successfully."}

@app.get("/api/progress/{user_id}/{book_id}", tags=["Reading Progress"])
async def get_progress(user_id: str, book_id: str):
    """
    Recupera el progreso de lectura del usuario para un libro específico.
    Si no se encuentra progreso, retorna la posición inicial por defecto.
    """
    progress = get_user_progress(user_id=user_id, book_id=book_id)
    if not progress:
        return {
            "user_id": user_id,
            "book_id": book_id,
            "current_element_id": 0,
            "char_offset": 0,
            "updated_at": ""
        }
    return progress

@app.get("/api/books/{task_id}/toc", tags=["PDF Processing"])
async def get_book_toc(task_id: str):
    """
    Lee el archivo JSON estructurado del libro (task_id) y extrae su tabla de contenidos (TOC)
    filtrando y buscando números romanos o títulos de capítulos.
    """
    task_dir = os.path.join(UPLOAD_DIR, task_id)
    if not os.path.exists(task_dir):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task directory for ID '{task_id}' not found."
        )
        
    try:
        files = os.listdir(task_dir)
        json_files = [f for f in files if f.endswith('.json')]
        if not json_files:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No structured JSON file found for task ID '{task_id}'."
            )
        json_path = os.path.join(task_dir, json_files[0])
        
        with open(json_path, 'r', encoding='utf-8') as f:
            book_data = json.load(f)
            
        elements = []
        if isinstance(book_data, dict):
            elements = book_data.get("kids", [])
        elif isinstance(book_data, list):
            elements = book_data
            
        toc = TOCService.extract_toc(elements)
        return {
            "task_id": task_id,
            "book_title": book_data.get("title", "") if isinstance(book_data, dict) else "",
            "toc": toc
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception(f"Error extracting TOC for task {task_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract Table of Contents: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
