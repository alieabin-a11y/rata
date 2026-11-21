from datetime import date, timedelta

import pandas as pd
import streamlit as st

import ai
import db
import files
import seed

st.set_page_config(page_title="Rata", page_icon="⚖️", layout="wide")
db.init_db()

NAV = ["1 · Buat Proyek", "2 · Dashboard", "3 · Laporan"]

MEMBER_DEFAULTS = ["Budi", "Sinta", "Raka", "Dewi", "Ayu"]
FORM_FIELDS = ["title", "desc", "n", "deadline"] + [f"member_{i}" for i in range(5)]

STATUS_EMOJI = {
    "TODO": "⬜",
    "READY": "🟦",
    "HELP": "🟨",
    "DECLINED": "🟧",
    "SUBMITTED": "🟪",
    "DONE": "🟩",
    "ESCALATED": "🟥",
}

STATUS_LABEL = {
    "TODO": "Belum mulai",
    "READY": "Siap dikerjakan",
    "HELP": "Butuh bantuan",
    "DECLINED": "Tidak bisa",
    "SUBMITTED": "Menunggu konfirmasi",
    "DONE": "Selesai & terverifikasi",
    "ESCALATED": "Tidak merespons",
}


def current_project_id():
    return st.session_state.get("project_id")


def _actor():
    """Identitas pelaku: dari token anggota, atau pratinjau ketua (simulasi)."""
    if st.session_state.get("actor_source") == "token" and st.session_state.get("actor_id"):
        return st.session_state["actor_id"], "token"
    return st.session_state.get("act_as"), "owner_preview"


def _actor_name() -> str:
    actor_id, source = _actor()
    if actor_id:
        pid = current_project_id()
        for m in db.get_members(pid) if pid else []:
            if m["id"] == actor_id:
                return m["name"]
    return "Pratinjau ketua"


def _is_url_valid(url: str) -> bool:
    if len(url) < 10 or not url.startswith(("http://", "https://")):
        return False
    host = url.split("//", 1)[-1].split("/", 1)[0]
    return "." in host and not host.endswith(".")


def _load_demo():
    new_pid = seed.load()
    st.session_state["project_id"] = new_pid
    st.session_state["project_select"] = new_pid
    st.session_state.pop("draft", None)
    st.session_state["flash"] = "Data demo dimuat."


def _clear_draft():
    st.session_state.pop("draft", None)


def _reset_form():
    st.session_state["title_store"] = ""
    st.session_state["desc_store"] = ""
    st.session_state["n_store"] = 3
    st.session_state["deadline_store"] = date.today() + timedelta(days=7)
    st.session_state["member_store"] = list(MEMBER_DEFAULTS)
    for field in FORM_FIELDS:
        st.session_state.pop(field, None)
    st.session_state.pop("file_note", None)


def _save_draft():
    draft = st.session_state.get("draft")
    if not draft:
        return
    plan = draft["plan"]
    pid = db.create_project(
        draft["title"], draft["description"], draft["deadline"], draft["members"][0]
    )
    mids = db.add_members(pid, draft["members"])
    db.add_tasks(pid, plan["tasks"], dict(zip(draft["members"], mids)))
    st.session_state["project_id"] = pid
    st.session_state["project_select"] = pid
    st.session_state.pop("draft", None)
    _reset_form()
    st.session_state["flash"] = "Proyek berhasil dibuat. Buka tab Dashboard."


def _goto(name: str):
    st.session_state["nav"] = name


def _set_status(task_id: str, status: str):
    actor_id, source = _actor()
    db.set_task_status(task_id, status, actor_id, source)
    st.session_state["flash_status"] = {
        "task_id": task_id,
        "status": status,
        "message": f"Status tugas diubah menjadi: {STATUS_LABEL.get(status, status)}.",
    }
    st.session_state["nav"] = NAV[1]


def _send_reply(task_id: str):
    text = (st.session_state.get(f"free_{task_id}") or "").strip()
    if not text:
        st.session_state["flash_status"] = {
            "task_id": task_id,
            "status": "error",
            "message": "Tulis balasan dulu sebelum mengirim.",
        }
        st.session_state["nav"] = NAV[1]
        return
    actor_id, source = _actor()
    tasks = db.get_tasks(st.session_state.get("project_id") or "")
    title = next((t["title"] for t in tasks if t["id"] == task_id), "Tugas")
    parsed = ai.parse_reply(text, title)
    db.reply_task(task_id, parsed["intent"], parsed["reason"], actor_id, source)
    st.session_state["flash_status"] = {
        "task_id": task_id,
        "status": parsed["intent"],
        "message": f"AI memahami balasan sebagai {STATUS_LABEL.get(parsed['intent'], parsed['intent'])} — {parsed['reason']}",
    }
    st.session_state["nav"] = NAV[1]


def _submit(task_id: str):
    url = (st.session_state.get(f"ev_{task_id}") or "").strip()
    hours_raw = st.session_state.get(f"hours_{task_id}")
    actor_id, source = _actor()

    if not _is_url_valid(url):
        message = "Tautan bukti wajib diisi dan harus berupa alamat http(s) yang valid."
    elif not hours_raw or float(hours_raw) <= 0:
        message = "Jam kerja aktual wajib diisi lebih dari 0."
    else:
        task = db.get_task(task_id)
        others = [
            t
            for t in db.get_tasks(st.session_state.get("project_id") or "")
            if t["id"] != task_id and (t.get("evidence_url") or "").strip() == url
        ]
        if others:
            message = (
                "Tautan ini sudah dipakai tugas lain "
                f"('{others[0]['title']}'). Setiap tugas butuh bukti sendiri."
            )
        else:
            db.submit_task(task_id, url, float(hours_raw), actor_id, source)
            st.session_state["flash_status"] = {
                "task_id": task_id,
                "status": "SUBMITTED",
                "message": (
                    f"Tugas '{task['title']}' dikumpulkan. Menunggu konfirmasi anggota lain "
                    "sebelum masuk hitungan kontribusi."
                ),
            }
            st.session_state["nav"] = NAV[1]
            return

    st.session_state["flash_status"] = {
        "task_id": task_id,
        "status": "error",
        "message": message,
    }
    st.session_state["nav"] = NAV[1]


def _verify(task_id: str):
    actor_id, source = _actor()
    task = db.get_task(task_id)
    if not actor_id:
        st.session_state["flash_status"] = {
            "task_id": task_id,
            "status": "error",
            "message": "Pilih anggota yang mengonfirmasi terlebih dahulu.",
        }
    elif not db.verify_task(task_id, actor_id, source):
        st.session_state["flash_status"] = {
            "task_id": task_id,
            "status": "error",
            "message": "Kamu tidak bisa mengonfirmasi tugasmu sendiri.",
        }
    else:
        st.session_state["flash_status"] = {
            "task_id": task_id,
            "status": "DONE",
            "message": f"'{task['title']}' dikonfirmasi selesai dan masuk hitungan kontribusi.",
        }
    st.session_state["nav"] = NAV[1]


def _reject(task_id: str):
    reason = (st.session_state.get(f"rej_{task_id}") or "").strip()
    actor_id, source = _actor()
    if len(reason) < 5:
        st.session_state["flash_status"] = {
            "task_id": task_id,
            "status": "error",
            "message": "Tulis alasan penolakan (minimal 5 karakter).",
        }
    else:
        db.reject_task(task_id, reason, actor_id, source)
        st.session_state["flash_status"] = {
            "task_id": task_id,
            "status": "READY",
            "message": "Tugas dikembalikan ke pemiliknya untuk diperbaiki.",
        }
    st.session_state["nav"] = NAV[1]


def _reopen(task_id: str):
    reason = (st.session_state.get(f"reopen_{task_id}") or "").strip()
    actor_id, source = _actor()
    if len(reason) < 5:
        st.session_state["flash_status"] = {
            "task_id": task_id,
            "status": "error",
            "message": "Tulis alasan pembukaan kembali (minimal 5 karakter).",
        }
    else:
        db.reopen_task(task_id, reason, actor_id, source)
        st.session_state["flash_status"] = {
            "task_id": task_id,
            "status": "READY",
            "message": "Tugas dibuka kembali dan dicabut dari hitungan kontribusi.",
        }
    st.session_state["nav"] = NAV[1]


def _simulate_24h():
    pid = st.session_state.get("project_id")
    if pid:
        changed = db.mark_escalated(pid)
        st.session_state["flash"] = f"{changed} tugas ditandai tidak merespons."
    st.session_state["nav"] = NAV[1]


def _load_file():
    up = st.session_state.get("upload")
    if not up:
        return
    text, note = files.extract_text(up.name, up.getvalue())
    if note:
        st.session_state["file_note"] = ("warning", note)
    else:
        st.session_state["desc_store"] = text
        st.session_state.pop("desc", None)
        st.session_state["file_note"] = (
            "success",
            f"{up.name} terbaca: {len(text)} karakter. Periksa kolom deskripsi sebelum membuat rencana.",
        )


def _clear_file():
    st.session_state["desc_store"] = ""
    st.session_state.pop("desc", None)
    st.session_state["file_note"] = ("info", "Isi file dihapus dari deskripsi.")


def build_report(project: dict, df: pd.DataFrame, total_tasks: int) -> str:
    lines = [f"# Laporan Kontribusi — {project['title']}", ""]
    lines.append(f"Deadline: {project['deadline']}")
    lines.append(f"Total tugas: {total_tasks}")
    lines.append("")
    lines.append("| Anggota | Terverifikasi | Total | Jam aktual | Jam estimasi | Kontribusi |")
    lines.append("|---|---|---|---|---|---|")
    for _, r in df.iterrows():
        lines.append(
            f"| {r['name']} | {int(r['done'])} | {int(r['total'])} | "
            f"{float(r['done_hours']):g} | {float(r['done_estimate']):g} | {r['kontribusi']}% |"
        )
    lines.append("")
    lines.append(f"**Total kontribusi: {df['kontribusi'].sum():.1f}%**")

    if not df.empty and int(df["pending"].sum()) > 0:
        lines.append("")
        lines.append(f"Menunggu konfirmasi: {int(df['pending'].sum())} tugas (belum dihitung).")

    verified = db.get_tasks(project["id"]) if project.get("id") else []
    verifiers: dict[str, int] = {}
    for t in verified:
        if t["status"] == "DONE" and t.get("verified_by"):
            verifiers[t["verified_by"]] = verifiers.get(t["verified_by"], 0) + 1
    if verifiers:
        names = {m["id"]: m["name"] for m in db.get_members(project["id"])}
        names["legacy"] = "data lama (sebelum verifikasi)"
        lines.append("")
        lines.append(
            "Konfirmasi oleh: "
            + ", ".join(f"{names.get(v, v)} ({c})" for v, c in verifiers.items())
        )

    anomalies = db.get_anomalies(project["id"]) if project.get("id") else []
    if anomalies:
        lines.append("")
        lines.append("**Sinyal perlu diperiksa:**")
        for a in anomalies:
            lines.append(f"- {a['jenis']}: {a['detail']}")

    lines.append("")
    lines.append(
        "_Kontribusi dihitung dari jam kerja aktual pada tugas yang dikonfirmasi "
        "anggota lain, bukan dari estimasi AI._"
    )
    lines.append("")
    lines.append("_Dibuat otomatis oleh Rata._")
    return "\n".join(lines)


# ------------------------------------------------------------------ identitas
# Token anggota dibaca sekali dari URL (?t=...), lalu disimpan di sesi.
_token = st.query_params.get("t")
if _token and "actor_id" not in st.session_state:
    _found = db.get_member_by_token(_token if isinstance(_token, str) else _token[0])
    if _found:
        st.session_state["actor_id"] = _found["id"]
        st.session_state["actor_source"] = "token"
        st.session_state["project_id"] = _found["project_id"]
        st.session_state["project_select"] = _found["project_id"]

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("## ⚖️ Rata")
    st.caption("Bukti kontribusi, bukan janji.")

    projects = db.list_projects()
    if projects:
        opts = {p["id"]: p["title"] for p in projects}
        ids = list(opts)
        pid_now = current_project_id()
        fallback = pid_now if pid_now in ids else ids[0]
        if st.session_state.get("project_select") not in ids:
            st.session_state["project_select"] = fallback
        chosen = st.selectbox(
            "Proyek aktif", ids, key="project_select", format_func=lambda x: opts[x]
        )
        st.session_state["project_id"] = chosen
    else:
        st.info("Belum ada proyek.")

    if st.button("Muat Data Demo", width="stretch", on_click=_load_demo):
        pass

    st.divider()

    actor_id, actor_source = _actor()
    if actor_source == "token" and actor_id:
        st.success(f"Bertindak sebagai **{_actor_name()}**")
    else:
        st.warning("Mode pratinjau ketua — aksi tercatat tanpa identitas anggota.")
        pid_sel = current_project_id()
        if pid_sel:
            _members = db.get_members(pid_sel)
            _names = {m["id"]: m["name"] for m in _members}
            if _names:
                if st.session_state.get("act_as") not in _names:
                    st.session_state["act_as"] = next(iter(_names))
                st.selectbox(
                    "Simulasikan sebagai",
                    list(_names),
                    format_func=lambda x: _names[x],
                    key="act_as",
                )
        st.caption("Bagikan tautan anggota agar status tercatat atas nama mereka.")

    pid_links = current_project_id()
    if pid_links and actor_source != "token":
        with st.expander("Tautan anggota"):
            st.caption("Bagikan hanya ke orang yang bersangkutan.")
            for m in db.get_members(pid_links):
                if m.get("token"):
                    st.caption(f"**{m['name']}**")
                    st.code(f"?t={m['token']}", language=None)

    st.divider()
    usage = db.get_ai_usage()
    st.caption(
        f"AI: {usage['calls']} panggilan · {int(usage['prompt']) + int(usage['completion'])} token"
    )

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

nav = st.radio(
    "Navigasi",
    NAV,
    horizontal=True,
    label_visibility="collapsed",
    key="nav",
)

# ------------------------------------------------------------------ tab 1
if nav == NAV[0]:
    st.subheader("Buat proyek tugas kelompok")

    if st.session_state.get("draft"):
        st.info(
            f"Rencana untuk \"{st.session_state['draft']['title']}\" sudah siap. "
            "Gulir ke bawah untuk menyimpan, atau buat rencana baru di bawah ini."
        )

    with st.container(border=True):
        for key, default in (
            ("title_store", ""),
            ("desc_store", ""),
            ("n_store", 3),
            ("deadline_store", date.today() + timedelta(days=7)),
            ("member_store", list(MEMBER_DEFAULTS)),
        ):
            if key not in st.session_state:
                st.session_state[key] = default
        if "title" not in st.session_state:
            st.session_state["title"] = st.session_state["title_store"]

        title = st.text_input(
            "Judul proyek",
            key="title",
            placeholder="Makalah Manajemen Strategi",
        )
        st.session_state["title_store"] = title

        st.markdown("**Bahan tugas**")
        st.caption("Unggah file tugas (PDF, DOCX, TXT, MD) atau tempel deskripsinya langsung.")
        up = st.file_uploader(
            "Unggah file tugas",
            type=["pdf", "docx", "txt", "md"],
            key="upload",
            label_visibility="collapsed",
        )
        u1, u2 = st.columns([1, 1])
        u1.button("Baca file", width="stretch", on_click=_load_file, disabled=up is None)
        u2.button("Hapus isi file", width="stretch", on_click=_clear_file)

        note = st.session_state.get("file_note")
        if note:
            kind, msg = note
            if kind == "success":
                st.success(msg)
            elif kind == "warning":
                st.warning(msg)
            else:
                st.info(msg)

        if "desc_store" not in st.session_state:
            st.session_state["desc_store"] = ""
        if "desc" not in st.session_state:
            st.session_state["desc"] = st.session_state["desc_store"]

        desc = st.text_area(
            "Deskripsi tugas",
            key="desc",
            height=170,
            placeholder="Contoh: Makalah 20 halaman tentang analisis strategi perusahaan teknologi",
        )
        st.session_state["desc_store"] = desc

        if "deadline" not in st.session_state:
            st.session_state["deadline"] = st.session_state["deadline_store"]
        deadline = st.date_input(
            "Deadline",
            key="deadline",
        )
        st.session_state["deadline_store"] = deadline

        if "n" not in st.session_state:
            st.session_state["n"] = st.session_state["n_store"]
        n = int(st.number_input("Jumlah anggota", min_value=1, max_value=5, key="n"))
        st.session_state["n_store"] = n

        cols = st.columns(n)
        names = []
        for i in range(n):
            field = f"member_{i}"
            if field not in st.session_state:
                st.session_state[field] = st.session_state["member_store"][i]
            names.append(cols[i].text_input(f"Anggota {i + 1}", key=field))
        st.session_state["member_store"] = list(names) + list(
            st.session_state["member_store"][n:]
        )

        if st.button("Buat Rencana dengan AI", type="primary"):
            clean = [x.strip() for x in names if x.strip()]
            if not title.strip() or len(desc.strip()) < 20 or not clean:
                st.error("Judul, deskripsi (minimal 20 karakter), dan nama anggota wajib diisi.")
            else:
                with st.spinner("AI sedang memecah tugas dan membagi beban..."):
                    plan = ai.generate_plan(desc.strip(), str(deadline), clean)
                st.session_state["draft"] = {
                    "title": title.strip(),
                    "description": desc.strip(),
                    "deadline": str(deadline),
                    "members": clean,
                    "plan": plan,
                }
                st.rerun()

    draft = st.session_state.get("draft")
    if draft:
        st.markdown("### Rencana dari AI")
        plan = draft["plan"]
        rows = [
            {
                "Tugas": t["title"],
                "PIC": t["assignee_name"],
                "Jam": t["estimate_hours"],
                "Prioritas": t["priority"],
            }
            for t in plan["tasks"]
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.info(plan.get("summary") or "Rencana siap disimpan.")

        if plan.get("source") == "fallback":
            st.warning("AI tidak tersedia saat ini — rencana dibuat dengan aturan dasar.")

        per_member = {}
        for t in plan["tasks"]:
            per_member[t["assignee_name"]] = per_member.get(t["assignee_name"], 0) + t["estimate_hours"]
        st.caption(
            "Beban per anggota: "
            + " · ".join(f"{k} {v} jam" for k, v in per_member.items())
        )

        c1, c2 = st.columns(2)
        c1.button("Simpan & Mulai", type="primary", width="stretch", on_click=_save_draft)
        c2.button("Batalkan", width="stretch", on_click=_clear_draft)

# ------------------------------------------------------------------ tab 2
if nav == NAV[1]:
    pid = current_project_id()
    project = db.get_project(pid) if pid else None

    if not project:
        st.info("Belum ada proyek aktif. Buat proyek di tab 1, atau klik **Muat Data Demo** di sidebar.")
    else:
        tasks = db.get_tasks(pid)
        members = db.get_members(pid)
        stats = db.project_stats(pid)
        df = db.contribution_df(pid)

        st.subheader(project["title"])
        st.caption(f"Deadline {project['deadline']} · {len(members)} anggota · {stats['total']} tugas")

        c = st.columns(4)
        c[0].metric("Total tugas", stats["total"])
        c[1].metric("Terverifikasi", stats["done"])
        c[2].metric("Menunggu konfirmasi", stats["pending"])
        c[3].metric("Butuh perhatian", stats["attention"])

        st.progress(stats["progress"])

        left, right = st.columns([1, 1.4])
        with left:
            st.markdown("#### Kontribusi")
            if not df.empty and float(df["done_hours"].sum()) > 0:
                st.bar_chart(df.set_index("name")["kontribusi"], height=260)
                st.caption("Dihitung dari jam kerja terverifikasi, bukan estimasi AI.")
            else:
                st.info(
                    "Belum ada tugas terverifikasi. Kontribusi muncul setelah tugas "
                    "dikumpulkan dengan bukti dan dikonfirmasi anggota lain."
                )

        with right:
            st.markdown("#### Tugas")
            tdf = pd.DataFrame(
                [
                    {
                        "Status": f"{STATUS_EMOJI.get(t['status'], '')} {STATUS_LABEL.get(t['status'], t['status'])}",
                        "Tugas": t["title"],
                        "PIC": t["assignee_name"] or "-",
                        "Jam": t["estimate_hours"],
                    }
                    for t in tasks
                ]
            )
            st.dataframe(tdf, hide_index=True, width="stretch")

        st.divider()

        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.markdown("#### Kirim ke Anggota · Panel Chat")
        with col_b:
            st.button("Simulasikan 24 Jam", width="stretch", on_click=_simulate_24h)

        flash_status = st.session_state.pop("flash_status", None)
        if flash_status:
            if flash_status["status"] == "error":
                st.error(flash_status["message"])
            else:
                st.success(flash_status["message"])

        if not members:
            st.info("Belum ada anggota.")
        else:
            actor_id, actor_source = _actor()
            names = {m["id"]: m["name"] for m in members}
            mine = [t for t in tasks if t["assignee_id"] == actor_id]
            pending = [
                t
                for t in tasks
                if t["status"] == "SUBMITTED" and t["assignee_id"] != actor_id
            ]

            if actor_id:
                st.caption(
                    f"Menampilkan tugas milik **{names.get(actor_id, 'anggota ini')}** "
                    f"· identitas: {'token' if actor_source == 'token' else 'pratinjau'}"
                )
            else:
                st.caption("Pilih anggota di sidebar untuk melihat tugasnya.")

            if not mine:
                st.caption("Anggota ini belum punya tugas.")
            for t in mine:
                label = f"{STATUS_EMOJI.get(t['status'], '')} {t['title']}"
                with st.expander(label, expanded=t["status"] != "DONE"):
                    st.chat_message("assistant").markdown(
                        f"**{t['title']}**  \n"
                        f"Estimasi {t['estimate_hours']} jam · Prioritas {t['priority']}  \n"
                        f"Status: {STATUS_LABEL.get(t['status'], t['status'])}"
                    )
                    if t.get("note"):
                        st.chat_message("user").markdown(str(t["note"]))
                    if t.get("evidence_url"):
                        st.caption(f"Bukti: {t['evidence_url']}")
                    if t.get("actual_hours"):
                        st.caption(f"Jam aktual dilaporkan: {t['actual_hours']:g} jam")
                    if t.get("reject_reason"):
                        st.warning(f"Catatan verifikator: {t['reject_reason']}")

                    if t["status"] == "DONE":
                        verifier = t.get("verified_by")
                        verifier_label = (
                            "data lama (sebelum verifikasi)"
                            if verifier == "legacy"
                            else names.get(verifier, "anggota lain")
                        )
                        st.success(f"Selesai dan terverifikasi oleh {verifier_label}.")
                        with st.expander("Buka kembali tugas ini"):
                            st.text_input(
                                "Alasan pembukaan kembali",
                                key=f"reopen_{t['id']}",
                                placeholder="Contoh: file yang dikirim salah versi",
                            )
                            st.button(
                                "Buka kembali",
                                key=f"reopenbtn_{t['id']}",
                                on_click=_reopen,
                                args=(t["id"],),
                            )
                    elif t["status"] == "SUBMITTED":
                        st.info("Menunggu konfirmasi anggota lain sebelum dihitung.")
                    else:
                        b1, b2, b3 = st.columns(3)
                        b1.button(
                            "SIAP",
                            key=f"ready_{t['id']}",
                            width="stretch",
                            on_click=_set_status,
                            args=(t["id"], "READY"),
                        )
                        b2.button(
                            "BUTUH BANTUAN",
                            key=f"help_{t['id']}",
                            width="stretch",
                            on_click=_set_status,
                            args=(t["id"], "HELP"),
                        )
                        b3.button(
                            "TIDAK BISA",
                            key=f"decline_{t['id']}",
                            width="stretch",
                            on_click=_set_status,
                            args=(t["id"], "DECLINED"),
                        )

                        st.text_input(
                            "atau balas dengan kalimat sendiri",
                            key=f"free_{t['id']}",
                            placeholder="Contoh: aku baru bisa minggu depan, lagi ada praktikum",
                        )
                        st.button(
                            "Kirim balasan",
                            key=f"send_{t['id']}",
                            on_click=_send_reply,
                            args=(t["id"],),
                        )

                        st.text_input(
                            "Tautan bukti (wajib)",
                            key=f"ev_{t['id']}",
                            value=t.get("evidence_url") or "",
                            placeholder="https://docs.google.com/...",
                        )
                        st.number_input(
                            "Jam kerja aktual (wajib)",
                            min_value=0.0,
                            max_value=200.0,
                            step=0.5,
                            key=f"hours_{t['id']}",
                            value=float(t.get("actual_hours") or 0.0),
                        )
                        st.button(
                            "Kumpulkan untuk verifikasi",
                            key=f"done_{t['id']}",
                            on_click=_submit,
                            args=(t["id"],),
                        )

            st.divider()
            st.markdown("#### Menunggu konfirmasi")
            if not pending:
                st.caption("Tidak ada tugas yang menunggu konfirmasi.")
            if not actor_id:
                st.caption("Pilih anggota di sidebar untuk bisa mengonfirmasi.")
            for t in pending:
                with st.expander(f"🟪 {t['title']} · {t['assignee_name']}"):
                    st.caption(
                        f"Bukti: {t['evidence_url']}  \n"
                        f"Jam dilaporkan: {t.get('actual_hours') or 0:g} jam "
                        f"(estimasi {t['estimate_hours']} jam)"
                    )
                    d1, d2 = st.columns(2)
                    d1.button(
                        "Konfirmasi selesai",
                        key=f"verify_{t['id']}",
                        width="stretch",
                        on_click=_verify,
                        args=(t["id"],),
                    )
                    st.text_input(
                        "Alasan penolakan (jika dikembalikan)",
                        key=f"rej_{t['id']}",
                        placeholder="Contoh: bukti hanya tautan kosong",
                    )
                    d2.button(
                        "Tolak & kembalikan",
                        key=f"reject_{t['id']}",
                        width="stretch",
                        on_click=_reject,
                        args=(t["id"],),
                    )

        st.divider()
        st.markdown("#### Rekam Jejak")
        anomalies = db.get_anomalies(pid)
        if anomalies:
            with st.expander(f"⚠️ {len(anomalies)} sinyal perlu diperiksa", expanded=True):
                for a in anomalies:
                    st.caption(f"**{a['jenis']}** — {a['detail']}")
        events = db.get_events(pid)
        if events:
            ev_df = pd.DataFrame(
                [
                    {
                        "Waktu": str(e["created_at"])[:19],
                        "Aktor": e["actor_name"] or "—",
                        "Aksi": STATUS_LABEL.get(e["type"], e["type"]),
                        "Tugas": e["task_title"],
                        "Detail": (e["detail"] or "")[:60],
                        "Sumber": (
                            "token"
                            if e["actor_source"] == "token"
                            else "sistem"
                            if e["actor_source"] == "system"
                            else "pratinjau"
                        ),
                    }
                    for e in events
                ]
            )
            st.dataframe(ev_df, hide_index=True, width="stretch")
        else:
            st.caption("Belum ada aktivitas tercatat.")

# ------------------------------------------------------------------ tab 3
if nav == NAV[2]:
    pid = current_project_id()
    project = db.get_project(pid) if pid else None

    if not project:
        st.info("Belum ada proyek aktif.")
    else:
        df = db.contribution_df(pid)
        tasks = db.get_tasks(pid)

        st.subheader("Laporan Kontribusi")
        st.caption(f"{project['title']} · deadline {project['deadline']}")

        show = df[["name", "done", "total", "pending", "done_hours", "done_estimate", "kontribusi"]].copy()
        show.columns = [
            "Anggota",
            "Terverifikasi",
            "Total tugas",
            "Menunggu konfirmasi",
            "Jam aktual",
            "Jam estimasi",
            "Kontribusi (%)",
        ]
        st.dataframe(show, hide_index=True, width="stretch")

        total = float(df["kontribusi"].sum()) if not df.empty else 0.0
        st.metric("Total kontribusi", f"{total:.1f}%")
        if abs(total - 100.0) > 0.5 and total > 0:
            st.warning("Total belum 100% — kemungkinan ada tugas tanpa penanggung jawab.")

        report = build_report(project, df, len(tasks))
        st.text_area("Ringkasan siap salin", report, height=220)
        st.download_button(
            "Unduh laporan .md",
            data=report,
            file_name="laporan-kontribusi.md",
            mime="text/markdown",
        )
