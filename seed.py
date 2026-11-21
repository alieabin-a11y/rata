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
        ("Slide presentasi", "Membuat 3 slide utama", 2, "MEDIUM", "SUBMITTED", "Budi",
         "https://docs.google.com/presentation/d/contoh-slide", None),
    ]

    # (status awal, jam aktual, verifikator) — DONE di demo harus sudah terverifikasi
    verified_hours = {"Riset & pengumpulan data": 3.0, "Menyusun latar belakang": 2.0, "Analisis SWOT": 3.0}
    verifier_for = {"Riset & pengumpulan data": "Sinta", "Menyusun latar belakang": "Sinta",
                    "Analisis SWOT": "Budi"}

    for i, (title, desc, hours, prio, status, name, evidence, note) in enumerate(tasks):
        tid = db.add_task(
            project_id=pid,
            title=title,
            description=desc,
            estimate_hours=hours,
            priority=prio,
            assignee_id=m[name],
            order_index=i,
            status="TODO" if status in ("DONE", "SUBMITTED") else status,
            evidence_url=None if status == "SUBMITTED" else evidence,
            note=note,
        )
        if status == "SUBMITTED":
            db.submit_task(tid, evidence, hours, m[name], "seed")
        elif status == "DONE":
            db.submit_task(tid, evidence, verified_hours[title], m[name], "seed")
            db.verify_task(tid, m[verifier_for[title]], "seed")

    # Sebarkan waktu verifikasi agar data demo tidak memicu sinyal
    # "verifikasi serentak" yang sebenarnya hanya artefak seed.
    conn = db.get_conn()
    try:
        for offset, title in enumerate(sorted(verified_hours)):
            conn.execute(
                "UPDATE tasks SET submitted_at=?, verified_at=? WHERE project_id=? AND title=?",
                (
                    f"2026-11-18 0{9 + offset}:20:00",
                    f"2026-11-18 {10 + offset}:05:00",
                    pid,
                    title,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return pid
