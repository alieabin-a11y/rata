PLAN_PROMPT = """Kamu adalah asisten manajemen proyek akademik.

Tugas kelompok: {description}
Deadline: {deadline}
Anggota: {members}
Jumlah anggota: {count}

Pecah pekerjaan menjadi subtask yang bisa diselesaikan satu orang dalam 1-4 jam,
lalu tentukan penanggung jawabnya secara seimbang.

Aturan:
- Jumlah tugas antara 4 dan 12
- Setiap tugas punya satu penanggung jawab dari daftar anggota
- Selisih total jam antar anggota maksimal 2 jam
- Setiap judul harus konkret dan bisa diverifikasi
- Urutkan sesuai urutan pengerjaan

Balas HANYA JSON valid dengan skema:
{{
  "tasks": [
    {{
      "title": "string",
      "description": "string",
      "estimate_hours": 2,
      "priority": "HIGH",
      "assignee_name": "nama dari daftar anggota"
    }}
  ],
  "summary": "satu kalimat ringkasan pembagian"
}}

Tanpa penjelasan, tanpa markdown, tanpa ```.
"""


PARSE_PROMPT = """Seorang anggota kelompok tugas membalas pesan tentang tugasnya.

Judul tugas: {task_title}
Balasan anggota: {text}

Tentukan niat anggota tersebut. Balas HANYA JSON valid:
{{
  "intent": "READY",
  "reason": "ringkasan alasan dalam bahasa Indonesia, maksimal 10 kata",
  "suggested_deadline": null
}}

Aturan nilai intent:
- READY  : anggota siap / sedang mengerjakan / akan selesai tepat waktu
- HELP   : anggota butuh bantuan, ada kendala, atau butuh waktu tambahan
- DECLINED: anggota menyatakan tidak bisa mengerjakan

suggested_deadline diisi "YYYY-MM-DD" hanya jika anggota menyebut waktu tertentu,
selain itu null. Tanpa penjelasan, tanpa markdown, tanpa ```.
"""
