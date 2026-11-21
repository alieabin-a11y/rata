from datetime import date, timedelta

import pandas as pd
import streamlit as st

import ai
import db
import seed

st.set_page_config(page_title="Rata", page_icon="⚖️", layout="wide")
db.init_db()

STATUS_EMOJI = {
    "TODO": "⬜",
    "READY": "🟦",
    "HELP": "🟨",
    "DECLINED": "🟧",
    "DONE": "🟩",
    "ESCALATED": "🟥",
}

STATUS_LABEL = {
    "TODO": "Belum mulai",
    "READY": "Siap dikerjakan",
    "HELP": "Butuh bantuan",
    "DECLINED": "Tidak bisa",
    "DONE": "Selesai",
    "ESCALATED": "Tidak merespons",
}


def current_project_id():
    return st.session_state.get("project_id")


def _load_demo():
    new_pid = seed.load()
    st.session_state["project_id"] = new_pid
    st.session_state["project_select"] = new_pid
    st.session_state.pop("draft", None)
    st.session_state["flash"] = "Data demo dimuat."


def _clear_draft():
    st.session_state.pop("draft", None)


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
    st.session_state["flash"] = "Proyek berhasil dibuat. Buka tab Dashboard."


def build_report(project: dict, df: pd.DataFrame, total_tasks: int) -> str:
    lines = [f"# Laporan Kontribusi — {project['title']}", ""]
    lines.append(f"Deadline: {project['deadline']}")
    lines.append(f"Total tugas: {total_tasks}")
    lines.append("")
    lines.append("| Anggota | Selesai | Total | Jam selesai | Kontribusi |")
    lines.append("|---|---|---|---|---|")
    for _, r in df.iterrows():
        lines.append(
            f"| {r['name']} | {int(r['done'])} | {int(r['total'])} | {r['done_hours']} | {r['kontribusi']}% |"
        )
    lines.append("")
    lines.append(f"**Total kontribusi: {df['kontribusi'].sum():.1f}%**")
    lines.append("")
    lines.append("_Dibuat otomatis oleh Rata._")
    return "\n".join(lines)


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
    usage = db.get_ai_usage()
    st.caption(
        f"AI: {usage['calls']} panggilan · {int(usage['prompt']) + int(usage['completion'])} token"
    )

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

tab1, tab2, tab3 = st.tabs(["1 · Buat Proyek", "2 · Dashboard", "3 · Laporan"])
# ------------------------------------------------------------------ tab 1
with tab1:
    st.subheader("Buat proyek tugas kelompok")

    with st.container(border=True):
        title = st.text_input("Judul proyek", placeholder="Makalah Manajemen Strategi")
        desc = st.text_area(
            "Deskripsi tugas",
            placeholder="Contoh: Makalah 20 halaman tentang analisis strategi perusahaan teknologi",
        )
        deadline = st.date_input("Deadline", value=date.today() + timedelta(days=7))
        n = int(st.number_input("Jumlah anggota", min_value=1, max_value=5, value=3))

        defaults = ["Budi", "Sinta", "Raka", "Dewi", "Ayu"]
        cols = st.columns(n)
        names = []
        for i in range(n):
            names.append(cols[i].text_input(f"Anggota {i + 1}", value=defaults[i], key=f"member_{i}"))

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
with tab2:
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
        c[1].metric("Selesai", stats["done"])
        c[2].metric("Berjalan", stats["running"])
        c[3].metric("Butuh perhatian", stats["attention"])

        st.progress(stats["progress"])

        left, right = st.columns([1, 1.4])
        with left:
            st.markdown("#### Kontribusi")
            if not df.empty:
                st.bar_chart(df.set_index("name")["kontribusi"], height=260)
                st.caption("Dihitung dari jam tugas yang benar-benar selesai.")
            else:
                st.caption("Belum ada data.")

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
            if st.button("Simulasikan 24 Jam", width="stretch"):
                changed = db.mark_escalated(pid)
                st.toast(f"{changed} tugas ditandai tidak merespons")
                st.rerun()

        if not members:
            st.info("Belum ada anggota.")
        else:
            names = {m["id"]: m["name"] for m in members}
            member_id = st.selectbox(
                "Pilih anggota", list(names), format_func=lambda x: names[x], key="chat_member"
            )
            mine = [t for t in tasks if t["assignee_id"] == member_id]

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

                    if t["status"] == "DONE":
                        st.success("Tugas ini sudah selesai dan buktinya tercatat.")
                    else:
                        b1, b2, b3 = st.columns(3)
                        if b1.button("SIAP", key=f"ready_{t['id']}", width="stretch"):
                            db.update_task_status(t["id"], "READY", member_id)
                            db.log_event(t["id"], member_id, "READY")
                            st.rerun()
                        if b2.button("BUTUH BANTUAN", key=f"help_{t['id']}", width="stretch"):
                            db.update_task_status(t["id"], "HELP", member_id)
                            db.log_event(t["id"], member_id, "HELP")
                            st.rerun()
                        if b3.button("TIDAK BISA", key=f"decline_{t['id']}", width="stretch"):
                            db.update_task_status(t["id"], "DECLINED", member_id)
                            db.log_event(t["id"], member_id, "DECLINED")
                            st.rerun()

                        free = st.text_input(
                            "atau balas dengan kalimat sendiri",
                            key=f"free_{t['id']}",
                            placeholder="Contoh: aku baru bisa minggu depan, lagi ada praktikum",
                        )
                        if st.button("Kirim balasan", key=f"send_{t['id']}"):
                            if not free.strip():
                                st.warning("Tulis balasan dulu.")
                            else:
                                parsed = ai.parse_reply(free, t["title"])
                                db.update_task_status(
                                    t["id"], parsed["intent"], member_id, note=parsed["reason"]
                                )
                                db.log_event(t["id"], member_id, parsed["intent"], parsed["reason"])
                                st.toast(f"AI memahami: {parsed['intent']} — {parsed['reason']}")
                                st.rerun()

                        ev = st.text_input(
                            "Tautan bukti (wajib untuk menyelesaikan)",
                            key=f"ev_{t['id']}",
                            value=t.get("evidence_url") or "",
                            placeholder="https://docs.google.com/...",
                        )
                        if st.button("Tandai SELESAI", key=f"done_{t['id']}"):
                            if not ev.strip():
                                st.warning("Tautan bukti wajib diisi sebelum menandai selesai.")
                            else:
                                db.update_task_status(
                                    t["id"], "DONE", member_id, evidence_url=ev.strip()
                                )
                                db.log_event(t["id"], member_id, "DONE", ev.strip())
                                st.rerun()

# ------------------------------------------------------------------ tab 3
with tab3:
    pid = current_project_id()
    project = db.get_project(pid) if pid else None

    if not project:
        st.info("Belum ada proyek aktif.")
    else:
        df = db.contribution_df(pid)
        tasks = db.get_tasks(pid)

        st.subheader("Laporan Kontribusi")
        st.caption(f"{project['title']} · deadline {project['deadline']}")

        show = df[["name", "done", "total", "done_hours", "kontribusi"]].copy()
        show.columns = ["Anggota", "Selesai", "Total tugas", "Jam selesai", "Kontribusi (%)"]
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
