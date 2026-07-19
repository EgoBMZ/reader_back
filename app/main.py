import os
import shutil
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from app.services.pdf_parser import PDFParserService
from app.services.pdf_reconstructor import PDFReconstructorService

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
