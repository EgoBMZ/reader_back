import os
import logging
from typing import List, Dict, Any
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logger = logging.getLogger(__name__)

class PDFReconstructorService:
    def __init__(self, static_dir: str, upload_dir: str):
        self.static_dir = static_dir
        self.upload_dir = upload_dir

    def reconstruct(self, document_data: List[Dict[str, Any]], task_id: str) -> str:
        """
        Reconstructs a PDF document from the structured elements and returns the output file path.
        """
        # Create output path
        output_filename = f"reconstructed_{task_id}.pdf"
        output_filepath = os.path.join(self.upload_dir, output_filename)
        
        logger.info(f"Reconstructing PDF to path: {output_filepath}")

        # Preprocess: Merge vertically adjacent sliced image bands into a single image to avoid white lines gap
        processed_elements = []
        i = 0
        while i < len(document_data):
            element = document_data[i]
            
            # Check if this element is an image
            if isinstance(element, dict) and (element.get("image_path") or element.get("src") or element.get("source") or (element.get("type") == "image" and element.get("path"))):
                next_element = document_data[i+1] if i+1 < len(document_data) else None
                merged = False
                
                while next_element and isinstance(next_element, dict) and (next_element.get("image_path") or next_element.get("src") or next_element.get("source") or (next_element.get("type") == "image" and next_element.get("path"))):
                    bbox1 = element.get("bounding box")
                    bbox2 = next_element.get("bounding box")
                    page1 = element.get("page number")
                    page2 = next_element.get("page number")
                    
                    if bbox1 and bbox2 and len(bbox1) == 4 and len(bbox2) == 4 and page1 == page2:
                        x0_1, y0_1, x1_1, y1_1 = bbox1
                        x0_2, y0_2, x1_2, y1_2 = bbox2
                        
                        # Check X alignment (approx same width and position)
                        x_aligned = abs(x0_1 - x0_2) < 3 and abs(x1_1 - x1_2) < 3
                        # Check vertical touch (one's bottom touches other's top)
                        y_touches = abs(y0_1 - y1_2) < 3 or abs(y1_1 - y0_2) < 3
                        
                        if x_aligned and y_touches:
                            try:
                                path1 = element.get("image_path") or element.get("src") or element.get("source") or element.get("path")
                                path2 = next_element.get("image_path") or next_element.get("src") or next_element.get("source") or next_element.get("path")
                                
                                fn1 = os.path.basename(path1)
                                fn2 = os.path.basename(path2)
                                
                                local_path1 = os.path.join(self.static_dir, "images", task_id, fn1)
                                local_path2 = os.path.join(self.static_dir, "images", task_id, fn2)
                                
                                if os.path.exists(local_path1) and os.path.exists(local_path2):
                                    from PIL import Image as PILImage
                                    img1 = PILImage.open(local_path1)
                                    img2 = PILImage.open(local_path2)
                                    
                                    # Y increases upwards in PDF. So larger Y is top image band.
                                    if y0_1 > y0_2:
                                        img_top, img_bottom = img1, img2
                                        new_bbox = [min(x0_1, x0_2), y0_2, max(x1_1, x1_2), y1_1]
                                    else:
                                        img_top, img_bottom = img2, img1
                                        new_bbox = [min(x0_1, x0_2), y0_1, max(x1_1, x1_2), y1_2]
                                        
                                    merged_width = max(img_top.width, img_bottom.width)
                                    merged_height = img_top.height + img_bottom.height
                                    
                                    merged_img = PILImage.new('RGBA', (merged_width, merged_height))
                                    merged_img.paste(img_top, (0, 0))
                                    merged_img.paste(img_bottom, (0, img_top.height))
                                    
                                    merged_filename = f"merged_{i}_{fn1}"
                                    merged_filepath = os.path.join(self.static_dir, "images", task_id, merged_filename)
                                    merged_img.save(merged_filepath)
                                    
                                    # Update current element with merged details
                                    merged_rel_path = f"/static/images/{task_id}/{merged_filename}"
                                    element["source"] = merged_rel_path
                                    element["image_path"] = merged_rel_path
                                    element["bounding box"] = new_bbox
                                    
                                    merged = True
                                    i += 1  # Skip the next element since it is now merged
                                    next_element = document_data[i+1] if i+1 < len(document_data) else None
                                    continue
                            except Exception as ex:
                                logger.error(f"Failed to merge adjacent images: {str(ex)}")
                                break
                    break
                
            processed_elements.append(element)
            i += 1
            
        document_data = processed_elements

        # Setup document
        doc = SimpleDocTemplate(
            output_filepath,
            pagesize=letter,
            rightMargin=54, # 0.75 inch
            leftMargin=54,
            topMargin=54,
            bottomMargin=54
        )

        # Setup styles
        styles = getSampleStyleSheet()
        
        # Add custom styles or modify existing ones to make them look nice
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#111827"), # Very dark gray (almost black)
            spaceBefore=14,
            spaceAfter=10,
            fontName='Helvetica-Bold'
        )
        
        heading2_style = ParagraphStyle(
            'CustomHeading2',
            parent=styles['Heading2'],
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#1f2937"), # Dark gray
            spaceBefore=10,
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )

        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['BodyText'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#374151"), # Charcoal text for reading comfort
            spaceAfter=6
        )

        story = []

        # Iterate elements and append flowables
        for element in document_data:
            if not isinstance(element, dict):
                continue
            
            el_type = element.get("type", "paragraph")
            text = element.get("text") or element.get("content") or ""
            
            # 1. Handle Images
            image_path = element.get("image_path") or element.get("src") or element.get("source") or (element.get("path") if el_type == "image" else None)
            if image_path:
                # We need to map the relative web URL (e.g. /static/images/{task_id}/{filename})
                # back to the absolute filesystem path
                filename = os.path.basename(image_path)
                local_image_path = os.path.join(self.static_dir, "images", task_id, filename)
                
                if os.path.exists(local_image_path):
                    try:
                        # ReportLab Image flowable
                        # Read dimensions or set default
                        # Standard letter size width is 612pt, margins are 54pt each, so printable width is 504pt
                        from PIL import Image as PILImage
                        with PILImage.open(local_image_path) as pil_img:
                            width, height = pil_img.size
                        
                        max_width = 450
                        max_height = 550 # Limit height to ensure it fits in vertical frame
                        
                        if width > max_width:
                            ratio = max_width / float(width)
                            width = max_width
                            height = int(height * ratio)
                            
                        if height > max_height:
                            ratio = max_height / float(height)
                            height = max_height
                            width = int(width * ratio)
                            
                        story.append(Image(local_image_path, width=width, height=height))
                        if text:
                            story.append(Paragraph(text, ParagraphStyle('Caption', parent=body_style, fontName='Helvetica-Oblique', alignment=1))) # Centered italic
                        story.append(Spacer(1, 10))
                    except Exception as e:
                        logger.error(f"Failed to embed image {local_image_path} in PDF: {str(e)}")
                continue

            # 2. Handle Headings
            if el_type.startswith("heading") or el_type in ["h1", "title"]:
                story.append(Paragraph(text, title_style if el_type == "title" else heading2_style))
                story.append(Spacer(1, 4))
                
            # 3. Handle Tables
            elif el_type == "table":
                headers = element.get("headers")
                rows = element.get("rows")
                
                if rows and isinstance(rows, list):
                    table_data = []
                    
                    # Style for table text
                    table_cell_style = ParagraphStyle(
                        'TableCell',
                        parent=body_style,
                        fontSize=9,
                        leading=11,
                        spaceAfter=0
                    )
                    table_header_style = ParagraphStyle(
                        'TableHeader',
                        parent=body_style,
                        fontSize=9,
                        leading=11,
                        textColor=colors.white,
                        fontName='Helvetica-Bold',
                        spaceAfter=0
                    )

                    # Add headers if present
                    if headers and isinstance(headers, list):
                        header_row = [Paragraph(str(h.get("text") if isinstance(h, dict) else h), table_header_style) for h in headers]
                        table_data.append(header_row)

                    for row in rows:
                        row_data = []
                        if isinstance(row, list):
                            for cell in row:
                                cell_text = str(cell.get("text") if isinstance(cell, dict) else cell)
                                row_data.append(Paragraph(cell_text, table_cell_style))
                        else:
                            cell_text = str(row.get("text") if isinstance(row, dict) else row)
                            row_data.append(Paragraph(cell_text, table_cell_style))
                        table_data.append(row_data)

                    # Determine width (let's divide printable area 504pt evenly among columns)
                    num_cols = len(table_data[0]) if table_data else 1
                    col_width = 504 / num_cols
                    
                    try:
                        t = Table(table_data, colWidths=[col_width] * num_cols)
                        
                        # Style table
                        t_style = [
                            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#d1d5db")),
                            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
                            ('VALIGN', (0,0), (-1,-1), 'TOP'),
                            ('TOPPADDING', (0,0), (-1,-1), 6),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                        ]
                        if headers:
                            t_style.append(('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f3f4f6")))
                            t_style.append(('TEXTCOLOR', (0,0), (-1,0), colors.HexColor("#111827")))
                        
                        t.setStyle(TableStyle(t_style))
                        story.append(t)
                        story.append(Spacer(1, 10))
                    except Exception as e:
                        logger.error(f"Failed to build table Flowable: {str(e)}")
                        
            # 4. Handle Paragraphs
            else:
                if text.strip():
                    story.append(Paragraph(text, body_style))
                    story.append(Spacer(1, 6))

        # Build document
        doc.build(story)
        return output_filepath
