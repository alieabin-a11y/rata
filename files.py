"""Pembaca file tugas: PDF, DOCX, TXT, MD.

Dipakai Tab 1 agar pengguna bisa mengunggah berkas tugas kuliah dan
membiarkan Rata membacanya, bukan menyalin-tempel manual.
"""

import io

MAX_CHARS = 6000
MIN_CHARS = 40


def _normalize(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _read_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _read_docx(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            parts.append(" | ".join(cells))
    return "\n".join(parts)


def extract_text(filename: str, data: bytes) -> tuple[str, str]:
    """Kembalikan (teks, catatan). Catatan kosong berarti berhasil."""
    name = (filename or "").lower()

    try:
        if name.endswith((".txt", ".md")):
            text = data.decode("utf-8", errors="replace")
        elif name.endswith(".pdf"):
            text = _read_pdf(data)
        elif name.endswith(".docx"):
            text = _read_docx(data)
        else:
            return "", "Format tidak didukung. Gunakan PDF, DOCX, TXT, atau MD."
    except ImportError as e:
        return "", f"Pustaka pembaca file belum terpasang ({e.name})."
    except Exception as e:
        return "", f"Gagal membaca file ({type(e).__name__}). Coba simpan ulang sebagai PDF atau TXT."

    text = _normalize(text)
    if len(text) < MIN_CHARS:
        return (
            "",
            "File terbaca tetapi teksnya terlalu sedikit. "
            "Kemungkinan hasil pindai/gambar. Salin isinya ke kolom deskripsi.",
        )

    return text[:MAX_CHARS], ""
