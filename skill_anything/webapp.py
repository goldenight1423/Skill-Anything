from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from skill_anything.engine import Engine

app = FastAPI(title="Skill-Anything Web UI")

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

STATE: dict[str, object] = {
    "message": "",
    "error": "",
    "title": "",
    "yaml_path": "",
    "quiz_questions": [],
    "flashcards": [],
}


def _set_message(message: str = "", error: str = "") -> None:
    STATE["message"] = message
    STATE["error"] = error


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "webui.html",
        {
            "api_key_configured": bool(os.getenv("SKILL_ANYTHING_API_KEY") or os.getenv("OPENAI_API_KEY")),
            "api_base": os.getenv("SKILL_ANYTHING_API_BASE") or os.getenv("OPENAI_API_BASE") or "",
            "model": os.getenv("SKILL_ANYTHING_MODEL", "gpt-4o"),
            **STATE,
        },
    )


@app.post("/config")
def save_config(
    api_key: str = Form(""),
    api_base: str = Form(""),
    model: str = Form("gpt-4o"),
) -> RedirectResponse:
    if api_key.strip():
        os.environ["SKILL_ANYTHING_API_KEY"] = api_key.strip()
    if api_base.strip():
        os.environ["SKILL_ANYTHING_API_BASE"] = api_base.strip()
    if model.strip():
        os.environ["SKILL_ANYTHING_MODEL"] = model.strip()

    _set_message("Configuracion guardada en memoria del contenedor.")
    return RedirectResponse(url="/", status_code=303)


@app.post("/generate")
async def generate_from_pdf(
    pdf_file: UploadFile = File(...),
    title: str = Form(""),
) -> RedirectResponse:
    if not pdf_file.filename.lower().endswith(".pdf"):
        _set_message(error="Solo se permiten archivos PDF.")
        return RedirectResponse(url="/", status_code=303)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = Path(pdf_file.filename).name
    saved_pdf = UPLOAD_DIR / f"{ts}-{safe_name}"

    content = await pdf_file.read()
    saved_pdf.write_bytes(content)

    try:
        engine = Engine()
        pack = engine.from_pdf(str(saved_pdf), title=title.strip() or None)
        engine.write(pack, OUTPUT_DIR, format="study")

        slug = pack.title.lower()
        slug = "-".join(part for part in "".join(ch if ch.isalnum() else " " for ch in slug).split())[:60]
        yaml_path = OUTPUT_DIR / f"{slug or 'skill-pack'}.yaml"

        STATE["title"] = pack.title
        STATE["yaml_path"] = str(yaml_path)
        STATE["quiz_questions"] = [q.to_dict() for q in pack.quiz_questions]
        STATE["flashcards"] = [f.to_dict() for f in pack.flashcards]
        _set_message("PDF procesado correctamente. Ya puedes revisar quiz y flashcards.")
    except Exception as exc:
        _set_message(error=f"Error al procesar PDF: {exc}")

    return RedirectResponse(url="/", status_code=303)


@app.post("/load-pack")
async def load_pack(yaml_file: UploadFile = File(...)) -> RedirectResponse:
    if not yaml_file.filename.lower().endswith((".yaml", ".yml")):
        _set_message(error="Sube un archivo .yaml o .yml")
        return RedirectResponse(url="/", status_code=303)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved_yaml = UPLOAD_DIR / f"{ts}-{Path(yaml_file.filename).name}"
    saved_yaml.write_bytes(await yaml_file.read())

    try:
        pack = Engine.load(str(saved_yaml))
        STATE["title"] = pack.title
        STATE["yaml_path"] = str(saved_yaml)
        STATE["quiz_questions"] = [q.to_dict() for q in pack.quiz_questions]
        STATE["flashcards"] = [f.to_dict() for f in pack.flashcards]
        _set_message("Pack cargado correctamente.")
    except Exception as exc:
        _set_message(error=f"No se pudo cargar el YAML: {exc}")

    return RedirectResponse(url="/", status_code=303)
