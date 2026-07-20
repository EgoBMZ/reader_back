import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Tesseract binary path (common Homebrew macOS location)
TESSERACT_PATH = "/opt/homebrew/bin/tesseract"


def _configure_pytesseract():
    """Import and configure pytesseract with proper binary path."""
    try:
        import pytesseract
        if os.path.exists(TESSERACT_PATH):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        return pytesseract
    except ImportError:
        logger.error("pytesseract is not installed. Run: pip install pytesseract")
        return None


class OCRService:
    """
    Servicio de Reconocimiento Óptico de Caracteres (OCR) para PDFs escaneados.
    
    Detecta automáticamente si un documento es un PDF escaneado (imágenes de páginas)
    y extrae el texto de las imágenes mediante Tesseract OCR.
    """

    # Umbral: si más del 70% de los elementos son imágenes sin texto → documento escaneado
    SCANNED_THRESHOLD = 0.70

    # Mínimo de caracteres de texto extraído para considerar que la imagen tiene texto real
    MIN_TEXT_CHARS = 15

    @classmethod
    def is_scanned_document(cls, elements: List[Dict[str, Any]]) -> bool:
        """
        Determina si el documento es un PDF escaneado analizando la proporción
        de imágenes vs. elementos con texto extraíble.

        Returns:
            True si el documento parece ser un conjunto de páginas escaneadas.
        """
        if not elements:
            return False

        total = len(elements)
        images = 0
        text_elements = 0

        for el in elements:
            el_type = el.get("type", "").lower()
            content = (el.get("content") or el.get("text") or "").strip()

            if el_type == "image":
                images += 1
            elif content:
                text_elements += 1

        # Evitar división por cero
        if total == 0:
            return False

        image_ratio = images / total

        logger.info(
            f"OCR Detection → total: {total}, images: {images}, "
            f"text_elements: {text_elements}, image_ratio: {image_ratio:.2f}"
        )

        # Si más del 70% son imágenes y hay muy poco texto, es escaneado
        return image_ratio >= cls.SCANNED_THRESHOLD and text_elements < 3

    @classmethod
    def apply_ocr_to_images(
        cls,
        elements: List[Dict[str, Any]],
        static_dir: str,
        lang: str = "spa+eng"
    ) -> List[Dict[str, Any]]:
        """
        Aplica OCR a todos los elementos de tipo imagen en el documento.

        Por cada imagen:
          - Si el OCR extrae texto significativo → convierte el elemento a párrafo.
          - Si la imagen no tiene texto real (ilustración, foto) → mantiene como imagen.

        Args:
            elements: Lista de elementos del JSON generado por opendataloader-pdf.
            static_dir: Ruta base del directorio de imágenes estáticas del servidor.
            lang: Idioma(s) para Tesseract OCR (ej: "spa+eng" para español e inglés).

        Returns:
            Lista de elementos con texto OCR inyectado donde corresponda.
        """
        pytesseract = _configure_pytesseract()
        if pytesseract is None:
            logger.warning("pytesseract no disponible. Saltando OCR.")
            return elements

        try:
            from PIL import Image
        except ImportError:
            logger.error("Pillow no está instalado. Run: pip install Pillow")
            return elements

        processed = []
        ocr_count = 0
        skipped_count = 0

        for element in elements:
            el_type = element.get("type", "").lower()

            if el_type != "image":
                processed.append(element)
                continue

            # Obtener la ruta de la imagen
            image_path = (
                element.get("source")
                or element.get("image_path")
                or element.get("src")
                or element.get("path")
            )

            if not image_path:
                processed.append(element)
                continue

            # Construir la ruta absoluta en el filesystem
            # La ruta en el JSON puede ser relativa (ej: "images/<task_id>/imageFile1.png")
            # o ya ser una URL /static/images/...
            abs_image_path = cls._resolve_image_path(image_path, static_dir)

            if not abs_image_path or not os.path.exists(abs_image_path):
                logger.debug(f"Imagen no encontrada en filesystem: {abs_image_path}")
                processed.append(element)
                continue

            # Aplicar OCR
            extracted_text = cls._extract_text_from_image(
                pytesseract, Image, abs_image_path, lang
            )

            if extracted_text and len(extracted_text.strip()) >= cls.MIN_TEXT_CHARS:
                # La imagen contiene texto → convertir a párrafo con OCR
                ocr_element = {
                    "type": "paragraph",
                    "id": element.get("id"),
                    "page number": element.get("page number"),
                    "content": extracted_text.strip(),
                    "ocr_extracted": True,
                    "original_image_source": image_path,
                }
                processed.append(ocr_element)
                ocr_count += 1
                logger.debug(
                    f"OCR exitoso en página {element.get('page number')}: "
                    f"{len(extracted_text)} chars extraídos"
                )
            else:
                # La imagen no tiene texto legible → mantener como imagen
                processed.append(element)
                skipped_count += 1

        logger.info(
            f"OCR completado → {ocr_count} imágenes convertidas a texto, "
            f"{skipped_count} imágenes sin texto mantenidas."
        )
        return processed

    @staticmethod
    def _resolve_image_path(image_path: str, static_dir: str) -> Optional[str]:
        """
        Resuelve la ruta de imagen desde el JSON a una ruta absoluta del filesystem.
        Maneja tanto rutas relativas como URLs internas (/static/...).
        """
        if not image_path:
            return None

        # Caso 1: URL interna tipo "/static/images/<task_id>/imageFile1.png"
        if image_path.startswith("/static/"):
            relative = image_path[len("/static/"):]  # Quitar el prefijo "/static/"
            return os.path.join(static_dir, relative)

        # Caso 2: Ruta relativa tipo "<task_id>/imageFile1.png"
        # El directorio estático de imágenes está en static_dir/images/
        candidate = os.path.join(static_dir, "images", image_path)
        if os.path.exists(candidate):
            return candidate

        # Caso 3: Ruta ya es absoluta
        if os.path.isabs(image_path) and os.path.exists(image_path):
            return image_path

        return None

    @staticmethod
    def _extract_text_from_image(
        pytesseract, Image, image_path: str, lang: str
    ) -> Optional[str]:
        """
        Ejecuta Tesseract OCR sobre una imagen y retorna el texto extraído.
        """
        try:
            img = Image.open(image_path)

            # Configuración de Tesseract optimizada para páginas de libros
            # PSM 6 = Assume a single uniform block of text (página de libro)
            custom_config = r"--oem 3 --psm 6"

            text = pytesseract.image_to_string(img, lang=lang, config=custom_config)
            return text

        except Exception as e:
            logger.debug(f"Error al aplicar OCR en {image_path}: {e}")
            return None
