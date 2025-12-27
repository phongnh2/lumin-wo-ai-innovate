import io
from typing import List, Dict
from PyPDF2 import PdfReader


class PDFProcessor:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract_text(self, pdf_content: bytes) -> str:
        pdf_file = io.BytesIO(pdf_content)
        reader = PdfReader(pdf_file)
        text_parts = []
        
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        
        return "\n".join(text_parts)

    def chunk_text(self, text: str, source: str) -> List[Dict]:
        chunks = []
        words = text.split()
        
        if not words:
            return chunks
        
        current_pos = 0
        chunk_id = 0
        
        while current_pos < len(words):
            end_pos = min(current_pos + self.chunk_size, len(words))
            chunk_words = words[current_pos:end_pos]
            chunk_text = " ".join(chunk_words)
            
            chunks.append({
                "id": f"{source}_{chunk_id}",
                "text": chunk_text,
                "source": source,
                "chunk_index": chunk_id
            })
            
            current_pos = end_pos - self.chunk_overlap if end_pos < len(words) else end_pos
            chunk_id += 1
        
        return chunks

