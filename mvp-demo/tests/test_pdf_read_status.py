import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pdf_read_status import inspect
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

class PDFReadingTests(unittest.TestCase):
    def test_scanned_or_blank_pdf_is_not_claimed_as_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'blank.pdf';writer=PdfWriter();writer.add_blank_page(width=600,height=800)
            with path.open('wb') as stream:writer.write(stream)
            result=inspect(path);self.assertEqual(result['status'],'scanned');self.assertEqual(result['text_pages'],0)

    def test_text_pdf_is_distinguished_from_numeric_table_reading(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'text.pdf';doc=canvas.Canvas(str(path));doc.drawString(30,600,'Sample paper without data table');doc.save()
            result=inspect(path);self.assertEqual(result['status'],'text');self.assertEqual(result['text_pages'],1)

    def test_encrypted_pdf_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'encrypted.pdf';writer=PdfWriter();writer.add_blank_page(width=600,height=800);writer.encrypt('secret')
            with path.open('wb') as stream:writer.write(stream)
            with self.assertRaises(ValueError):inspect(path)

if __name__=='__main__':unittest.main()
