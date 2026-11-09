"""Public synthetic PDF fixture; never reads a personal report."""
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject

def write_fixture_pdf(path):
    writer=PdfWriter();font=writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')}))
    for number in range(1,4):
        page=writer.add_blank_page(595,842);page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 68 738 Td (An eror. Synthetic page {number}.) Tj ET'.encode());page[NameObject('/Contents')]=writer._add_object(stream)
    writer.write(path)
