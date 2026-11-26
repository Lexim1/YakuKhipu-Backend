"""Comprueba lectura digital y OCR real de un PDF mixto con Poppler y Tesseract."""
import shutil
import subprocess

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from app.worker_pdf import extraer


def stream(page, writer, contenido):
    datos = DecodedStreamObject()
    datos.set_data(contenido)
    page[NameObject("/Contents")] = writer._add_object(datos)


def digital(writer):
    pagina = writer.add_blank_page(width=595, height=842)
    fuente = DictionaryObject({NameObject("/Type"):NameObject("/Font"),
        NameObject("/Subtype"):NameObject("/Type1"), NameObject("/BaseFont"):NameObject("/Helvetica")})
    pagina[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"):DictionaryObject({NameObject("/F1"):fuente})})
    stream(pagina, writer, b"BT /F1 34 Tf 75 690 Td (Expediente de prueba) Tj ET")


def test_lectura_y_ocr_por_pagina(tmp_path):
    if not all(shutil.which(x) for x in ("pdfinfo", "pdftotext", "pdftoppm", "tesseract")):
        pytest.skip("Requiere Poppler y Tesseract con idioma spa.")
    writer = PdfWriter()
    digital(writer)
    digital_pdf = tmp_path / "digital.pdf"
    writer.write(digital_pdf)
    archivo = tmp_path / "escaneo"
    subprocess.run(["pdftoppm","-gray","-singlefile","-scale-to","1300",str(digital_pdf),str(archivo)],
                   check=True, timeout=30)
    magic, dimensiones, maxima, pixeles = archivo.with_suffix(".pgm").read_bytes().split(b"\n", 3)
    assert (magic, maxima) == (b"P5", b"255")
    ancho, alto = map(int, dimensiones.split())
    escaneada = writer.add_blank_page(width=595, height=842)
    imagen = DecodedStreamObject()
    imagen.set_data(pixeles)
    imagen.update({NameObject("/Type"):NameObject("/XObject"), NameObject("/Subtype"):NameObject("/Image"),
                   NameObject("/ColorSpace"):NameObject("/DeviceGray"), NameObject("/BitsPerComponent"):NumberObject(8),
                   NameObject("/Width"):NumberObject(ancho), NameObject("/Height"):NumberObject(alto)})
    escaneada[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"):DictionaryObject({NameObject("/I1"):writer._add_object(imagen)})})
    stream(escaneada, writer, b"q 595 0 0 842 0 0 cm /I1 Do Q")
    mixto = tmp_path / "mixto.pdf"
    writer.write(mixto)
    paginas = extraer(mixto, tmp_path)
    assert [p["origen"] for p in paginas] == ["texto_pdf", "ocr"]
    assert all("Expediente de prueba" in p["texto"] for p in paginas)
