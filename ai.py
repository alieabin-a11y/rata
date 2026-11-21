import json
import os

from openai import OpenAI

import db
from prompts import PLAN_PROMPT, PARSE_PROMPT

BASE_URL = "https://tokengateway.dev/v1"
MODEL = "deepseek-v4.1-flash"

_client: OpenAI | None = None


def _api_key() -> str:
    try:
        import streamlit as st

        if "TOKENGATEWAY_API_KEY" in st.secrets:
            return st.secrets["TOKENGATEWAY_API_KEY"]
    except Exception:
        pass
    return os.environ.get("TOKENGATEWAY_API_KEY", "")


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=BASE_URL, api_key=_api_key(), timeout=90.0)
    return _client


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _valid_plan(data: dict, members: list[str]) -> bool:
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not 2 <= len(tasks) <= 15:
        return False
    for t in tasks:
        if not isinstance(t, dict) or not str(t.get("title", "")).strip():
            return False
        if not isinstance(t.get("estimate_hours", 2), (int, float)):
            return False
    return True


def _normalize_plan(data: dict, members: list[str]) -> dict:
    tasks = []
    for t in data["tasks"]:
        name = str(t.get("assignee_name", "")).strip()
        if name not in members:
            name = members[0]
        hours = float(t.get("estimate_hours", 2))
        hours = max(0.5, min(4.0, hours))
        prio = str(t.get("priority", "MEDIUM")).upper()
        if prio not in ("HIGH", "MEDIUM", "LOW"):
            prio = "MEDIUM"
        tasks.append(
            {
                "title": str(t.get("title", "Tugas")).strip(),
                "description": str(t.get("description", "")).strip(),
                "estimate_hours": hours,
                "priority": prio,
                "assignee_name": name,
            }
        )
    return {"tasks": tasks, "summary": str(data.get("summary", "")).strip()}


def fallback_plan(description: str, members: list[str]) -> dict:
    base = [
        ("Riset & pengumpulan bahan", "Mencari minimal 3 sumber yang relevan", 3, "HIGH"),
        ("Menyusun kerangka", "Membuat struktur dan pembagian bab", 2, "HIGH"),
        ("Menulis isi", "Menulis isi utama sesuai kerangka", 4, "MEDIUM"),
        ("Revisi & format akhir", "Memeriksa konsistensi, format, dan daftar pustaka", 2, "LOW"),
        ("Menyiapkan presentasi", "Membuat slide dan poin utama", 2, "MEDIUM"),
    ]
    tasks = []
    for i, (title, desc, hours, prio) in enumerate(base):
        tasks.append(
            {
                "title": title,
                "description": desc,
                "estimate_hours": hours,
                "priority": prio,
                "assignee_name": members[i % len(members)],
            }
        )
    return {
        "tasks": tasks,
        "summary": "Rencana dasar dibuat otomatis karena AI tidak tersedia.",
        "source": "fallback",
        "usage": {"prompt": 0, "completion": 0},
    }


def generate_plan(description: str, deadline: str, members: list[str]) -> dict:
    if not members:
        members = ["Anggota 1"]

    prompt = PLAN_PROMPT.format(
        description=description,
        deadline=deadline,
        members=", ".join(members),
        count=len(members),
    )

    for attempt in range(2):
        try:
            resp = client().chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
            )
            raw = resp.choices[0].message.content or ""
            data = _extract_json(raw)
            if data and _valid_plan(data, members):
                usage = resp.usage
                db.log_ai_run("PLAN", MODEL, usage.prompt_tokens, usage.completion_tokens)
                result = _normalize_plan(data, members)
                result["source"] = "ai"
                result["usage"] = {
                    "prompt": usage.prompt_tokens,
                    "completion": usage.completion_tokens,
                }
                return result
            prompt += "\n\nJSON sebelumnya tidak valid. Perbaiki dan balas hanya JSON valid."
        except Exception:
            if attempt == 1:
                break
    return fallback_plan(description, members)


def _heuristic_intent(text: str) -> str:
    low = text.lower()
    if any(w in low for w in ("tidak bisa", "gak bisa", "nggak bisa", "tidak sanggup")):
        return "DECLINED"
    if any(
        w in low
        for w in (
            "bantu",
            "kendala",
            "sibuk",
            "praktikum",
            "minggu depan",
            "belum",
            "telat",
            "terlambat",
            "sulit",
            "tidak sempat",
            "gak sempat",
        )
    ):
        return "HELP"
    if any(w in low for w in ("siap", "oke", "ok", "sudah", "selesai", "bisa")):
        return "READY"
    return "HELP"


def parse_reply(text: str, task_title: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {"intent": "HELP", "reason": "Balasan kosong", "suggested_deadline": None}

    prompt = PARSE_PROMPT.format(task_title=task_title, text=text)
    try:
        resp = client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500,
        )
        raw = resp.choices[0].message.content or ""
        data = _extract_json(raw)
        if data and str(data.get("intent", "")).upper() in ("READY", "HELP", "DECLINED"):
            usage = resp.usage
            db.log_ai_run("PARSE", MODEL, usage.prompt_tokens, usage.completion_tokens)
            return {
                "intent": str(data["intent"]).upper(),
                "reason": str(data.get("reason", ""))[:160],
                "suggested_deadline": data.get("suggested_deadline"),
                "source": "ai",
            }
    except Exception:
        pass

    return {
        "intent": _heuristic_intent(text),
        "reason": text[:160],
        "suggested_deadline": None,
        "source": "fallback",
    }
