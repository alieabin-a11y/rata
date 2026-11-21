# Rata — PRD (ringkas)

**Versi:** 3.0 · **Konteks:** CAKREN HACKSPACE 2026 · **Tim:** 1 orang
**Bentuk:** Web app (Streamlit) · **Deploy:** GitHub → Streamlit Cloud

---

## 1. Masalah

Dalam tugas kelompok, kontribusi anggota tidak terlihat dan tidak tertagih. Akibatnya satu atau dua orang mengerjakan seluruh beban, sementara nilai dibagi rata. Mahasiswa menghabiskan waktu berjam-jam hanya untuk mengejar anggota lain.

**Empat akar masalah:**

| # | Akar masalah | Dijawab oleh |
|---|---|---|
| 1 | Tidak ada rekam jejak kontribusi | Skor kontribusi + laporan |
| 2 | Konfrontasi sosial dihindari | AI menyusun kalimat penagihan |
| 3 | Tugas tidak terpecah jelas | Dekomposisi tugas otomatis |
| 4 | Tidak ada sistem pengingat | Status + eskalasi |

**Framing produk:** bukan alat memaksa orang bekerja, tapi alat **membuktikan kontribusi**.

> "Kelompok yang adil tidak butuh orang baik. Butuh sistem."

---

## 2. Pengguna

| Persona | Kebutuhan | Peran |
|---|---|---|
| Ketua kelompok | Kerja dibagi adil tanpa harus menegur | Membuat proyek, memantau dashboard |
| Anggota aktif | Kontribusinya diakui | Menerima tugas, mengubah status |
| Anggota pasif | Diingatkan tanpa dipermalukan | Status tercatat otomatis |
| Dosen | Bukti kontribusi saat menilai | Menerima laporan |

---

## 3. Ruang lingkup

### P0 — wajib selesai
1. Buat proyek + anggota
2. AI memecah tugas + membagi beban (satu panggilan)
3. Dashboard: metrik, progress, chart kontribusi
4. Panel chat per anggota + tombol status
5. AI membaca balasan bebas
6. Tautan bukti wajib untuk status selesai
7. Laporan + unduh `.md`
8. Data demo sekali klik
9. Deploy publik

### Stretch (hanya jika buffer utuh)
- AI draft pesan teguran
- Halaman usage token
- Edit tugas manual

### Tidak dikerjakan
Bot Telegram · login · upload file · realtime · notifikasi email · dark mode

---

## 4. Alur utama

```
1. Ketua isi form: judul, deskripsi tugas, deadline, anggota
2. Klik "Buat Rencana dengan AI" → daftar tugas + PIC + estimasi jam
3. Klik "Simpan & Mulai" → dashboard aktif
4. Anggota membalas: tombol (SIAP/BANTU/TIDAK BISA) atau kalimat bebas
5. AI membaca balasan bebas → menentukan status + alasan
6. Status selesai hanya bisa jika ada tautan bukti
7. Laporan kontribusi dibuat otomatis dan bisa diunduh
```

---

## 5. AI

| Fungsi | Input | Output | Fallback |
|---|---|---|---|
| `generate_plan` | deskripsi, deadline, anggota | daftar tugas + PIC + jam + prioritas (JSON) | 5 tugas generik dibagi bergiliran |
| `parse_reply` | kalimat bebas anggota | intent (READY/HELP/DECLINED) + alasan + saran deadline | heuristik kata kunci |

**Aturan:** temperature 0.3, max 2 percobaan, timeout 30 detik, semua panggilan mencatat token ke tabel `ai_runs`.

---

## 6. Kriteria selesai

- [ ] Bisa buat proyek dari nol < 3 menit
- [ ] AI menghasilkan minimal 4 tugas dengan PIC
- [ ] Selisih jam antar anggota ≤ 2 jam
- [ ] Menekan tombol mengubah status di dashboard
- [ ] Balasan bebas diproses AI
- [ ] Status selesai terkunci tanpa tautan bukti
- [ ] Chart kontribusi total 100%
- [ ] Laporan bisa diunduh `.md`
- [ ] Tombol "Muat Data Demo" berfungsi
- [ ] App bisa dibuka dari HP
- [ ] Fallback AI terbukti jalan saat key dimatikan
- [ ] Video 75 detik & slide PDF terunggah sebelum 14.15

---

## 7. Batas waktu

| Pukul | Jika belum | Tindakan |
|---|---|---|
| 11.50 | Dashboard belum jalan | Pakai data demo statis |
| 12.55 | Chat panel belum jalan | Ganti dengan tabel status |
| 13.45 | Buffer habis | **Berhenti coding**, rekam video |
| 14.15 | — | **Code freeze** |

**Aturan:** demo 3 menit hanya melewati satu jalur: Buat → AI → Dashboard → Chat → Laporan.
