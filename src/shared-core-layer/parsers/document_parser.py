"""Document parsers for PDF and DOCX files."""

import base64
import fitz  # PyMuPDF
from docx import Document
from io import BytesIO
from typing import List


def extract_text_from_pdf(pdf_data: bytes) -> str:
    """Extract text from PDF bytes.
    
    Args:
        pdf_data: PDF file as bytes
    
    Returns:
        Extracted text from all pages
    """
    text = ""
    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
    for page in pdf_document:
        text += page.get_text()
    return text


def extract_text_from_docx(docx_bytes: bytes) -> str:
    """Extract text from DOCX bytes.
    
    Args:
        docx_bytes: DOCX file as bytes
    
    Returns:
        Extracted text from all paragraphs
    """
    text = ""
    document = Document(BytesIO(docx_bytes))
    for paragraph in document.paragraphs:
        text += paragraph.text + "\n"
    return text


def extract_images_from_pdf(pdf_bytes: bytes) -> List[str]:
    """Extract images from PDF as base64 strings.
    
    Args:
        pdf_bytes: PDF file as bytes
    
    Returns:
        List of base64-encoded PNG images (one per page)
    """
    print('called extract_images_from_pdf')
    images_base64 = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    print('doc opened')
    
    for page in doc:
        print('started loop')
        
        pix = page.get_pixmap(dpi=150)
        image_bytes = pix.tobytes("png")
        
        img_str = base64.b64encode(image_bytes).decode("utf-8")
        
        images_base64.append(img_str)
    
    print('images_base64 len', len(images_base64))
    
    return images_base64
