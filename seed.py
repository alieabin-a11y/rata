import db


def load() -> str:
    """Buat proyek contoh yang sudah terisi, tanpa memanggil AI."""
    db.reset_all()

    pid = db.create_project(
        "Makalah Manajemen Strategi",
        "Makalah 20 halaman tentang analisis strategi perusahaan teknologi di Indonesia",
        "2026-11-28",
        "Ketua Kelompok",
    )

    names = ["Budi", "Sinta", "Raka"]
    mids = db.add_members(pid, names)
    m = dict(zip(names, mids))

    tasks = [
        ("Riset & pengumpulan data", "Mengumpulkan 5 sumber kredibel", 3, "HIGH", "DONE", "Budi",
         "https://docs.google.com/document/d/contoh-riset", None),
        ("Menyusun latar belakang", "Menulis 1 halaman latar belakang", 2, "HIGH", "DONE", "Budi",
         "https://docs.google.com/document/d/contoh-latar", None),
        ("Analisis SWOT", "Menyusun matriks SWOT lengkap", 3, "HIGH", "DONE", "Sinta",
         "https://docs.google.com/document/d/contoh-swot", None),
        ("Bab pembahasan", "Menulis 5 halaman pembahasan", 4, "MEDIUM", "READY", "Sinta", None, None),
        ("Kesimpulan & rekomendasi", "Merangkum temuan dan saran", 2, "MEDIUM", "HELP", "Raka", None,
         "Butuh bantuan mencari data pendukung"),
        ("Revisi & format akhir", "Cek konsistensi dan daftar pustaka", 2, "LOW", "ESCALATED", "Raka",
         None, "Belum ada balasan"),
        ("Slide presentasi", "Membuat 3 slide utama", 2, "MEDIUM", "TODO", "Budi", None, None),
    ]

    for i, (title, desc, hours, prio, status, name, evidence, note) in enumerate(tasks):
        db.add_task(
            project_id=pid,
            title=title,
            description=desc,
            estimate_hours=hours,
            priority=prio,
            assignee_id=m[name],
            order_index=i,
            status=status,
            evidence_url=evidence,
            note=note,
        )

    return pid
