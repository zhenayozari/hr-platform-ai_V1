from typing import Optional
from fastapi import Query

import os
import httpx
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel, Field

from .database import get_db, init_db
from .models import Vacancy, Candidate, Company
from .ai import analyze_resume_with_gpt, generate_vacancy_description 

app = FastAPI(
    title="HR Платформа API v1.0",
    description="Документация API для автоматизации рекрутинга",
    version="1.0.0"
)

# --- НАСТРОЙКА CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SCHEMAS ---

class VacancyGenerate(BaseModel):
    title: str
    requirements: str
    company_id: int

class CandidateUpdate(BaseModel):
    status: str

class VacancyCreate(BaseModel):
    title: str = Field(..., title="Название вакансии")
    description: str = Field(..., title="Описание")
    requirements: str = Field(..., title="Требования")
    company_id: int = Field(..., title="ID Компании")

class VacancyResponse(VacancyCreate):
    id: int
    status: str
    class Config:
        from_attributes = True

class CandidateApply(BaseModel):
    vacancy_id: int
    first_name: str
    last_name: str = ""
    username: str = ""
    resume_text: str

class CandidateResponse(BaseModel):
    id: int
    ai_score: float
    ai_summary: str
    status: str
    first_name: str
    last_name: str
    vacancy_id: int
    vacancy_title: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class VacancyDetailResponse(BaseModel):
    id: int
    title: str
    description: str
    requirements: str
    status: str
    candidates_count: int
    candidates_by_status: dict
    
    class Config:
        from_attributes = True

# --- НОВЫЕ СХЕМЫ ДЛЯ ДЕТАЛЬНОЙ КАРТОЧКИ ---
class CommentCreate(BaseModel):
    text: str
    author_name: str = "HR Admin"

class CandidateDetailResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    telegram_id: Optional[str] = None
    resume_text: str
    ai_score: float
    ai_summary: str
    status: str
    source: str
    vacancy_id: int
    vacancy_title: str
    created_at: datetime
    comments: List[dict]
    activities: List[dict]
    
    class Config:
        from_attributes = True


# --- ENDPOINTS ---

@app.on_event("startup")
def on_startup():
    init_db()

@app.post("/vacancies/", response_model=VacancyResponse)
def create_vacancy(vacancy: VacancyCreate, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == vacancy.company_id).first()
    if not company:
        company = Company(id=vacancy.company_id, name="Test Company")
        db.add(company)
        db.commit()
    
    db_vacancy = Vacancy(**vacancy.dict())
    db.add(db_vacancy)
    db.commit()
    db.refresh(db_vacancy)
    return db_vacancy

@app.get("/vacancies/", response_model=List[VacancyResponse])
def read_vacancies(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    vacancies = db.query(Vacancy).offset(skip).limit(limit).all()
    return vacancies

@app.post("/vacancies/generate", response_model=VacancyResponse)
def generate_vacancy(params: VacancyGenerate, db: Session = Depends(get_db)):
    ai_data = generate_vacancy_description(params.title, params.requirements)
    
    conditions_text = ai_data.get('conditions', [])
    if isinstance(conditions_text, list):
        conditions_text = "\n".join([f"- {c}" for c in conditions_text])
    
    full_description = f"{ai_data.get('description', '')}\n\nУсловия:\n{conditions_text}"
    
    requirements_list = ai_data.get('requirements', [])
    if isinstance(requirements_list, list):
        full_requirements = "\n".join([f"- {r}" for r in requirements_list])
    else:
        full_requirements = str(requirements_list)
    
    company = db.query(Company).filter(Company.id == params.company_id).first()
    if not company:
        company = Company(id=params.company_id, name="My Company")
        db.add(company)
        db.commit()

    db_vacancy = Vacancy(
        title=params.title,
        description=full_description,
        requirements=full_requirements,
        company_id=params.company_id,
        status="active"
    )
    db.add(db_vacancy)
    db.commit()
    db.refresh(db_vacancy)
    return db_vacancy


@app.post("/candidates/apply", response_model=CandidateResponse)
def apply_candidate(application: CandidateApply, db: Session = Depends(get_db)):
    vacancy = db.query(Vacancy).filter(Vacancy.id == application.vacancy_id).first()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")

    full_vacancy_text = f"{vacancy.title}\n{vacancy.description}\n{vacancy.requirements}"
    ai_result = analyze_resume_with_gpt(application.resume_text, full_vacancy_text)

    db_candidate = Candidate(
        first_name=application.first_name,
        last_name=application.last_name,
        telegram_id=application.username,
        email="tg_user@example.com",
        resume_text=application.resume_text,
        vacancy_id=application.vacancy_id,
        ai_score=ai_result.get("score", 0),
        ai_summary=ai_result.get("summary", "Ошибка анализа"),
        status="screening"
    )
    
    db.add(db_candidate)
    db.commit()
    db.refresh(db_candidate)
    
    return {
        "id": db_candidate.id,
        "ai_score": db_candidate.ai_score,
        "ai_summary": db_candidate.ai_summary,
        "status": db_candidate.status,
        "first_name": db_candidate.first_name,
        "last_name": db_candidate.last_name,
        "vacancy_id": db_candidate.vacancy_id,
        "vacancy_title": vacancy.title,
        "created_at": db_candidate.created_at
    }

# --- ОБНОВЛЕННЫЙ ЭНДПОИНТ СМЕНЫ СТАТУСА (С ИСТОРИЕЙ) ---
@app.patch("/candidates/{candidate_id}", response_model=CandidateResponse)
async def update_candidate_status(candidate_id: int, status_update: CandidateUpdate, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")
    
    old_status = candidate.status
    candidate.status = status_update.status
    
    # --- ЛОГИРОВАНИЕ В ИСТОРИЮ ---
    from .models import CandidateActivity
    if old_status != status_update.status:
        activity = CandidateActivity(
            candidate_id=candidate_id,
            action="status_change",
            description=f"Статус изменен: {old_status} -> {status_update.status}"
        )
        db.add(activity)
    # -----------------------------

    db.commit()
    db.refresh(candidate)

    # Уведомление в Telegram
    if status_update.status == "interview" and candidate.telegram_id:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if token:
            msg = f"🎉 <b>{candidate.first_name}, хорошие новости!</b>\nМы приглашаем вас на интервью."
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            async with httpx.AsyncClient() as client:
                try:
                    await client.post(url, json={"chat_id": candidate.telegram_id, "text": msg, "parse_mode": "HTML"})
                except: pass

    # Возвращаем объект (Pydantic сам достанет vacancy_title, если в модели есть property или relationship)
    # Если в модели нет vacancy_title, здесь нужно вручную сформировать dict, как в apply_candidate
    vac_title = candidate.vacancy.title if candidate.vacancy else "Архив"
    return {
        "id": candidate.id,
        "ai_score": candidate.ai_score,
        "ai_summary": candidate.ai_summary,
        "status": candidate.status,
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "vacancy_id": candidate.vacancy_id,
        "vacancy_title": vac_title,
        "created_at": candidate.created_at
    }

@app.get("/candidates/", response_model=List[CandidateResponse])
def read_candidates(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    candidates = db.query(Candidate).offset(skip).limit(limit).all()
    result = []
    for c in candidates:
        vac_title = c.vacancy.title if c.vacancy else "Архив/Без вакансии"
        result.append({
            "id": c.id,
            "ai_score": c.ai_score,
            "ai_summary": c.ai_summary,
            "status": c.status,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "vacancy_id": c.vacancy_id,
            "vacancy_title": vac_title,
            "created_at": c.created_at
        })
    return result

@app.get("/vacancies/{vacancy_id}", response_model=VacancyDetailResponse)
def get_vacancy_detail(vacancy_id: int, db: Session = Depends(get_db)):
    vacancy = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    
    candidates = db.query(Candidate).filter(Candidate.vacancy_id == vacancy_id).all()
    
    status_counts = {}
    for c in candidates:
        status_counts[c.status] = status_counts.get(c.status, 0) + 1
    
    return {
        "id": vacancy.id,
        "title": vacancy.title,
        "description": vacancy.description,
        "requirements": vacancy.requirements,
        "status": vacancy.status,
        "candidates_count": len(candidates),
        "candidates_by_status": status_counts
    }

@app.get("/vacancies/{vacancy_id}/candidates", response_model=List[CandidateResponse])
def get_vacancy_candidates(vacancy_id: int, db: Session = Depends(get_db)):
    vacancy = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    
    candidates = db.query(Candidate).filter(Candidate.vacancy_id == vacancy_id).all()
    
    result = []
    for c in candidates:
        result.append({
            "id": c.id,
            "ai_score": c.ai_score,
            "ai_summary": c.ai_summary,
            "status": c.status,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "vacancy_id": c.vacancy_id,
            "vacancy_title": vacancy.title,
            "created_at": c.created_at
        })
    return result


# --- ЭНДПОИНТЫ ДЛЯ ПОИСКА ---

class CandidateListResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    telegram_id: Optional[str] = None
    ai_score: float
    ai_summary: str
    status: str
    source: str
    vacancy_id: int
    vacancy_title: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class CandidatesListWithPagination(BaseModel):
    items: List[CandidateListResponse]
    total: int
    page: int
    per_page: int
    pages: int

@app.get("/candidates/search", response_model=CandidatesListWithPagination)
def search_candidates(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    vacancy_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    query = db.query(Candidate)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Candidate.first_name.ilike(search_term)) |
            (Candidate.last_name.ilike(search_term)) |
            (Candidate.email.ilike(search_term))
        )
    if status:
        query = query.filter(Candidate.status == status)
    if source:
        query = query.filter(Candidate.source == source)
    if vacancy_id:
        query = query.filter(Candidate.vacancy_id == vacancy_id)
    
    total = query.count()
    query = query.order_by(Candidate.created_at.desc())
    offset = (page - 1) * per_page
    candidates = query.offset(offset).limit(per_page).all()
    
    items = []
    for c in candidates:
        items.append({
            "id": c.id,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "email": c.email,
            "phone": c.phone,
            "telegram_id": c.telegram_id,
            "ai_score": c.ai_score,
            "ai_summary": c.ai_summary,
            "status": c.status,
            "source": c.source,
            "vacancy_id": c.vacancy_id,
            "vacancy_title": c.vacancy.title if c.vacancy else "Архив",
            "created_at": c.created_at
        })
    
    pages = (total + per_page - 1) // per_page
    return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": pages}

@app.get("/candidates/stats")
def get_candidates_stats(db: Session = Depends(get_db)):
    candidates = db.query(Candidate).all()
    if not candidates:
        return {"total": 0, "avg_score": 0}
    
    avg_score = sum(c.ai_score for c in candidates) / len(candidates)
    return {
        "total": len(candidates),
        "avg_score": round(avg_score, 1)
    }

# --- ЭНДПОИНТЫ ДЛЯ ДЕТАЛЬНОЙ КАРТОЧКИ ---

@app.get("/candidates/{candidate_id}/detail", response_model=CandidateDetailResponse)
def get_candidate_detail(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")
    
    # Собираем комментарии
    comments = []
    for c in candidate.comments:
        comments.append({
            "id": c.id,
            "author_name": c.author_name,
            "text": c.text,
            "created_at": c.created_at.isoformat()
        })
    
    # Собираем историю
    activities = []
    for a in candidate.activities:
        activities.append({
            "id": a.id,
            "action": a.action,
            "description": a.description,
            "created_at": a.created_at.isoformat()
        })
    
    return {
        "id": candidate.id,
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "email": candidate.email,
        "phone": candidate.phone,
        "telegram_id": candidate.telegram_id,
        "resume_text": candidate.resume_text,
        "ai_score": candidate.ai_score,
        "ai_summary": candidate.ai_summary,
        "status": candidate.status,
        "source": candidate.source,
        "vacancy_id": candidate.vacancy_id,
        "vacancy_title": candidate.vacancy.title if candidate.vacancy else "Архив",
        "created_at": candidate.created_at,
        "comments": comments,
        "activities": activities
    }

@app.post("/candidates/{candidate_id}/comments")
def add_comment(candidate_id: int, comment: CommentCreate, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")
    
    # 1. Создаем комментарий
    from .models import CandidateComment, CandidateActivity 
    
    db_comment = CandidateComment(
        candidate_id=candidate_id,
        author_name=comment.author_name,
        text=comment.text
    )
    db.add(db_comment)
    
    # 2. Пишем в историю
    activity = CandidateActivity(
        candidate_id=candidate_id,
        action="comment",
        description=f"Добавлен комментарий: {comment.text[:20]}..."
    )
    db.add(activity)
    
    db.commit()
    return {"status": "ok"}