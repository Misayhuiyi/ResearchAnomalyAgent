"""Text-only PDF capability probe in a resource-limited child; no OCR or model."""
import json
import sys
from pathlib import Path
from source_catalog import limit_reader_memory

class EncryptedPDF(ValueError):pass

def inspect(path):
    from pypdf import PdfReader
    reader=PdfReader(path,strict=True)
    if reader.is_encrypted:raise EncryptedPDF('Encrypted PDF')
    if len(reader.pages)>200:return {'status':'limited','pages':len(reader.pages)}
    chars=0;text_pages=0;scanned=[]
    for index,page in enumerate(reader.pages,1):
        text=page.extract_text() or '';size=len(text.strip());chars+=size
        if size:text_pages+=1
        else:scanned.append(index)
        if chars>240000:return {'status':'limited','pages':len(reader.pages),'text_pages':text_pages}
    return {'status':'text' if text_pages else 'scanned','pages':len(reader.pages),'text_pages':text_pages,'empty_text_pages':scanned}

if __name__=='__main__':
    guard=limit_reader_memory()
    try:answer=inspect(Path(sys.argv[1]))
    except EncryptedPDF:answer={'status':'encrypted'}
    except Exception:answer={'status':'unavailable'}
    print(json.dumps(answer))
