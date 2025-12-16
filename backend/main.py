from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from datetime import datetime
import os
import httpx

from .database import get_db, init_db
from .models import Vacancy, Candidate, Company, User, CandidateActivity, CandidateComment, PipelineStage, EmailTemplate
from .ai import analyze_resume_with_gpt, generate_vacancy_description

# Auth
from .auth.router import router as auth_router
from .auth.dependencies import get_current_user, check_company_access

# Settings
from .routers.settings import router as settings_router

app = FastAPI(
    title="HR Платформа API v2.0",
    description="API с авторизацией и мультитенантностью",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(settings_router)

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/")
def root():
    return {"message": "HR Platform API v2.0 is running"}

# --- SCHEMAS (Схемы данных) ---

# --- ВАКАНСИИ (ОБНОВЛЕНО) ---
class VacancyCreate(BaseModel):
    title: str = Field(..., title="Название")
    requirements: str = Field(..., title="Требования")
    # Новые поля (опциональные)
    description: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    experience: Optional[str] = None
    employment_type: Optional[str] = None
    city: Optional[str] = None

class VacancyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    status: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    experience: Optional[str] = None
    employment_type: Optional[str] = None
    city: Optional[str] = None

class VacancyResponse(VacancyCreate):
    id: int
    status: str
    company_id: int
    class Config:
        from_attributes = True

class VacancyDetailResponse(VacancyResponse):
    candidates_count: int
    candidates_by_status: dict

# Кандидаты
class CandidateApply(BaseModel):
    vacancy_id: int
    first_name: str
    last_name: str = ""
    username: str = ""
    resume_text: str

class CandidateUpdate(BaseModel):
    status: str

class CommentCreate(BaseModel):
    text: str
    author_name: str = "HR"

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

    # ЭТОТ ВАЛИДАТОР ЧИНИТ ОШИБКУ 500
    @validator("vacancy_title", pre=True, always=True)
    def get_vacancy_title(cls, v, values):
        if isinstance(v, str):
            return v
        return "Вакансия" # Заглушка, если название не нашлось

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

# Дашборд
class DashboardStats(BaseModel):
    active_vacancies: int
    candidates_in_work: int
    hired_this_month: int
    conversion_rate: float
    funnel_stats: dict
    recent_activities: List[dict]
    urgent_candidates: List[dict]

# --- ENDPOINTS (Защищенные) ---

# 1. ВАКАНСИИ

@app.post("/vacancies/", response_model=VacancyResponse)
def create_vacancy(
    vacancy: VacancyCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_vacancy = Vacancy(
        **vacancy.dict(),
        company_id=current_user.company_id,
        status="active"
    )
    db.add(db_vacancy)
    db.commit()
    db.refresh(db_vacancy)
    return db_vacancy

# --- ОБНОВЛЕННЫЙ ЭНДПОИНТ ГЕНЕРАЦИИ (СОХРАНЯЕТ В БД) ---
@app.post("/vacancies/generate", response_model=VacancyResponse)
def generate_vacancy(
    params: VacancyCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Формируем строку зарплаты для AI
    salary_str = ""
    if params.salary_min and params.salary_max:
        salary_str = f"{params.salary_min} - {params.salary_max} руб."
    elif params.salary_min:
        salary_str = f"от {params.salary_min} руб."
    
    # Вызываем AI с новыми параметрами
    ai_data = generate_vacancy_description(
        title=params.title, 
        requirements=params.requirements,
        salary=salary_str,
        city=params.city or "Не указан",
        experience=params.experience or "Любой"
    )
    
    # Форматируем текст
    conditions_text = ai_data.get('conditions', [])
    if isinstance(conditions_text, list):
        conditions_text = "\n".join([f"- {c}" for c in conditions_text])
    
    full_description = f"{ai_data.get('description', '')}\n\nУсловия:\n{conditions_text}"
    
    requirements_list = ai_data.get('requirements', [])
    if isinstance(requirements_list, list):
        full_requirements = "\n".join([f"- {r}" for r in requirements_list])
    else:
        full_requirements = str(requirements_list)

    db_vacancy = Vacancy(
        title=params.title,
        description=full_description,
        requirements=full_requirements,
        salary_min=params.salary_min,
        salary_max=params.salary_max,
        experience=params.experience,
        employment_type=params.employment_type,
        city=params.city,
        company_id=current_user.company_id,
        status="active"
    )
    db.add(db_vacancy)
    db.commit()
    db.refresh(db_vacancy)
    return db_vacancy

# --- НОВЫЙ ЭНДПОИНТ ПРЕДПРОСМОТРА (НЕ СОХРАНЯЕТ В БД) ---
@app.post("/vacancies/preview_ai")
def preview_vacancy_ai(
    params: VacancyCreate, 
    current_user: User = Depends(get_current_user)
):
    """
    Генерирует описание вакансии, но НЕ сохраняет в базу.
    Нужно для предпросмотра в форме создания.
    """
    # Формируем строку зарплаты
    salary_str = ""
    if params.salary_min and params.salary_max:
        salary_str = f"{params.salary_min} - {params.salary_max} руб."
    elif params.salary_min:
        salary_str = f"от {params.salary_min} руб."
    
    # Вызываем AI
    ai_data = generate_vacancy_description(
        title=params.title, 
        requirements=params.requirements,
        salary=salary_str,
        city=params.city or "Не указан",
        experience=params.experience or "Любой"
    )
    
    # Формируем красивый текст
    conditions_text = ai_data.get('conditions', [])
    if isinstance(conditions_text, list):
        conditions_text = "\n".join([f"- {c}" for c in conditions_text])
    
    full_description = f"{ai_data.get('description', '')}\n\nУсловия:\n{conditions_text}"
    
    # Возвращаем только текст
    return {"description": full_description}

# --- ПУБЛИЧНЫЙ ЭНДПОИНТ ДЛЯ БОТА ---
@app.get("/public/vacancies", response_model=List[VacancyResponse])
def get_public_vacancies(db: Session = Depends(get_db)):
    """
    Отдает все активные вакансии всех компаний.
    Нужен для Telegram-бота, чтобы кандидаты могли выбирать работу.
    """
    return db.query(Vacancy).filter(Vacancy.status == "active").all()

@app.get("/vacancies/", response_model=List[VacancyResponse])
def read_vacancies(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Фильтруем по компании пользователя
    vacancies = db.query(Vacancy).filter(
        Vacancy.company_id == current_user.company_id
    ).offset(skip).limit(limit).all()
    return vacancies

@app.get("/vacancies/{vacancy_id}", response_model=VacancyDetailResponse)
def get_vacancy_detail(
    vacancy_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    vacancy = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    check_company_access(vacancy, current_user, "Вакансия") # Проверка доступа
    
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
        "company_id": vacancy.company_id,
        "salary_min": vacancy.salary_min,
        "salary_max": vacancy.salary_max,
        "experience": vacancy.experience,
        "employment_type": vacancy.employment_type,
        "city": vacancy.city,
        "candidates_count": len(candidates),
        "candidates_by_status": status_counts
    }

# --- НОВЫЙ ЭНДПОИНТ РЕДАКТИРОВАНИЯ ---
@app.patch("/vacancies/{vacancy_id}", response_model=VacancyResponse)
def update_vacancy(
    vacancy_id: int,
    data: VacancyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    vacancy = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    check_company_access(vacancy, current_user, "Вакансия")
    
    for field, value in data.dict(exclude_unset=True).items():
        setattr(vacancy, field, value)
    
    db.commit()
    db.refresh(vacancy)
    return vacancy

@app.get("/vacancies/{vacancy_id}/candidates", response_model=List[CandidateResponse])
def get_vacancy_candidates(
    vacancy_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    vacancy = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    check_company_access(vacancy, current_user, "Вакансия")
    
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

# 2. КАНДИДАТЫ

# Публичный метод (для бота) - БЕЗ current_user
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
        company_id=vacancy.company_id, 
        ai_score=ai_result.get("score", 0),
        ai_summary=ai_result.get("summary", "Ошибка анализа"),
        status="new",
        source="telegram"
    )
    
    db.add(db_candidate)
    
    # Лог активности
    activity = CandidateActivity(
        candidate=db_candidate,
        action="apply",
        description="Кандидат откликнулся через Telegram"
    )
    db.add(activity)
    
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

# ПОИСК КАНДИДАТОВ (Для вкладки "Кандидаты")
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
    current_user: User = Depends(get_current_user),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    vacancy_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    query = db.query(Candidate).filter(
        Candidate.company_id == current_user.company_id
    )
    
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
def get_candidates_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    candidates = db.query(Candidate).filter(Candidate.company_id == current_user.company_id).all()
    scores = [c.ai_score for c in candidates if c.ai_score]
    avg_score = sum(scores) / len(scores) if scores else 0
    return {
        "total": len(candidates),
        "avg_score": round(avg_score, 1)
    }

@app.get("/candidates/{candidate_id}/detail", response_model=CandidateDetailResponse)
def get_candidate_detail(
    candidate_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    check_company_access(candidate, current_user, "Кандидат")
    
    comments = [{"id": c.id, "author_name": c.author_name, "text": c.text, "created_at": c.created_at} for c in candidate.comments]
    activities = [{"id": a.id, "action": a.action, "description": a.description, "created_at": a.created_at} for a in candidate.activities]
    
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

@app.patch("/candidates/{candidate_id}", response_model=CandidateResponse)
async def update_candidate_status(
    candidate_id: int, 
    status_update: CandidateUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    check_company_access(candidate, current_user, "Кандидат")
    
    old_status = candidate.status
    if old_status != status_update.status:
        candidate.status = status_update.status
        # Лог
        db.add(CandidateActivity(
            candidate_id=candidate.id,
            action="status_change",
            description=f"Статус изменен: {old_status} -> {status_update.status}"
        ))
        
        # Уведомление
        if status_update.status == "interview" and candidate.telegram_id:
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            if token:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                async with httpx.AsyncClient() as client:
                    try:
                        await client.post(url, json={
                            "chat_id": candidate.telegram_id, 
                            "text": f"🎉 {candidate.first_name}, вас пригласили на интервью!",
                            "parse_mode": "HTML"
                        })
                    except: pass

    db.commit()
    db.refresh(candidate)
    
    # РУЧНОЙ ВОЗВРАТ ДАННЫХ (чтобы не было ошибки 500)
    return {
        "id": candidate.id,
        "ai_score": candidate.ai_score,
        "ai_summary": candidate.ai_summary,
        "status": candidate.status,
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "vacancy_id": candidate.vacancy_id,
        "vacancy_title": candidate.vacancy.title if candidate.vacancy else "Архив",
        "created_at": candidate.created_at
    }

@app.post("/candidates/{candidate_id}/comments")
def add_comment(
    candidate_id: int, 
    comment: CommentCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    check_company_access(candidate, current_user, "Кандидат")
    
    db.add(CandidateComment(candidate_id=candidate_id, author_name=comment.author_name, text=comment.text))
    db.add(CandidateActivity(candidate_id=candidate_id, action="comment", description=f"Комментарий: {comment.text[:20]}..."))
    db.commit()
    return {"status": "ok"}

# 3. ДАШБОРД

@app.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from datetime import timedelta
    
    # Фильтруем ВСЕ запросы по company_id
    active_vacancies = db.query(Vacancy).filter(
        Vacancy.company_id == current_user.company_id, 
        Vacancy.status == "active"
    ).count()
    
    candidates_in_work = db.query(Candidate).filter(
        Candidate.company_id == current_user.company_id,
        Candidate.status.notin_(["hired", "rejected", "new"])
    ).count()
    
    hired_this_month = db.query(Candidate).filter(
        Candidate.company_id == current_user.company_id,
        Candidate.status == "hired"
    ).count()
    
    total_candidates = db.query(Candidate).filter(Candidate.company_id == current_user.company_id).count()
    total_hired = db.query(Candidate).filter(Candidate.company_id == current_user.company_id, Candidate.status == "hired").count()
    conversion = (total_hired / total_candidates * 100) if total_candidates > 0 else 0
    
    # Воронка
    statuses = ["new", "screening", "interview", "offer", "hired", "rejected"]
    funnel = {}
    for s in statuses:
        funnel[s] = db.query(Candidate).filter(
            Candidate.company_id == current_user.company_id,
            Candidate.status == s
        ).count()
        
    # Активность
    recent_activities = [] 
    
    urgent = db.query(Candidate).filter(
        Candidate.company_id == current_user.company_id,
        Candidate.status == "new"
    ).limit(5).all()
    
    urgent_list = [{"id": c.id, "name": f"{c.first_name} {c.last_name}", "vacancy": c.vacancy.title, "days": (datetime.utcnow()-c.created_at).days} for c in urgent]

    return {
        "active_vacancies": active_vacancies,
        "candidates_in_work": candidates_in_work,
        "hired_this_month": hired_this_month,
        "conversion_rate": round(conversion, 1),
        "funnel_stats": funnel,
        "recent_activities": recent_activities,
        "urgent_candidates": urgent_list
    }