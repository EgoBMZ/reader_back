import re
from typing import List, Dict, Any

class TOCService:
    # Expresión regular para números romanos puros (ej. "I", "II", "XIV", "xx")
    ROMAN_REGEX = re.compile(r'^[ivxldmc]+$', re.IGNORECASE)
    
    # Expresión regular para indicar capítulo (ej. "Capítulo I", "Capítulo 1", "Chapter II", "Cap. 3: El inicio")
    CHAPTER_INDICATOR_REGEX = re.compile(
        r'^(cap[íi]tulo|chapter|secci[óo]n|section|cap\.)\s+(\d+|[ivxldmc]+)\b.*$', 
        re.IGNORECASE
    )
    
    # Expresión regular para títulos numerados (ej. "1. Introducción", "I. El principio", "1 - Prólogo")
    NUMBERED_HEADING_REGEX = re.compile(
        r'^(\d+|[ivxldmc]+)\s*[\.\-:]\s+(.+)$', 
        re.IGNORECASE
    )

    @classmethod
    def is_chapter_heading(cls, text: str) -> bool:
        """
        Determina si el contenido de un texto coincide con patrones típicos de capítulos.
        """
        text_strip = text.strip()
        if not text_strip:
            return False
            
        # 1. Comprobar si es un número romano exacto
        if cls.ROMAN_REGEX.match(text_strip):
            return True
            
        # 2. Comprobar si inicia con indicador de capítulo (ej. "Capítulo 4")
        if cls.CHAPTER_INDICATOR_REGEX.match(text_strip):
            return True
            
        # 3. Comprobar si inicia con número o romano seguido de separador (ej. "1. Introducción")
        if cls.NUMBERED_HEADING_REGEX.match(text_strip):
            return True
            
        return False

    @classmethod
    def extract_toc(cls, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analiza los elementos estructurados del documento y extrae aquellos que representen capítulos.
        
        Parámetros:
            elements: Una lista de diccionarios, cada uno representando un elemento del PDF (del JSON generado).
            
        Retorna:
            Una lista de diccionarios con el id del elemento, título del capítulo y número de página.
        """
        toc = []
        for element in elements:
            if not isinstance(element, dict):
                continue
                
            element_type = element.get("type", "").lower()
            # Generalmente OpenDataLoader detecta los títulos como "heading" o "subtitle"
            if element_type in ("heading", "subtitle") or element.get("heading level") is not None:
                content = element.get("content", "")
                
                if cls.is_chapter_heading(content):
                    toc.append({
                        "element_id": element.get("id"),
                        "title": content.strip(),
                        "page_number": element.get("page number"),
                        "type": element_type
                    })
        return toc
