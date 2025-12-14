import os
import httpx
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # <--- НОВЫЙ ИМПОРТ
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

# --- НАСТРОЙКА CORS (ЧТОБЫ ФРОНТЕНД РАБОТАЛ) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешаем всем (для разработки)
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
    # 1. Генерируем текст через AI
    ai_data = generate_vacancy_description(params.title, params.requirements)
    
    # 2. Собираем красивый текст
    # ИСПРАВЛЕНИЕ: Превращаем список условий в строку, если это список
    conditions_text = ai_data.get('conditions', [])
    if isinstance(conditions_text, list):
        conditions_text = "\n".join([f"- {c}" for c in conditions_text])
    
    full_description = f"{ai_data.get('description', '')}\n\nУсловия:\n{conditions_text}"
    
    # ИСПРАВЛЕНИЕ: Превращаем список требований в строку с буллитами
    requirements_list = ai_data.get('requirements', [])
    if isinstance(requirements_list, list):
        full_requirements = "\n".join([f"- {r}" for r in requirements_list])
    else:
        full_requirements = str(requirements_list)
    
    # 3. Создаем компанию если нет
    company = db.query(Company).filter(Company.id == params.company_id).first()
    if not company:
        company = Company(id=params.company_id, name="My Company")
        db.add(company)
        db.commit()

    # 4. Сохраняем в базу
    db_vacancy = Vacancy(
        title=params.title,
        description=full_description,
        requirements=full_requirements, # Теперь тут строка, а не список!
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
    
    return db_candidate

@app.patch("/candidates/{candidate_id}", response_model=CandidateResponse)
async def update_candidate_status(candidate_id: int, status_update: CandidateUpdate, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")
    
    candidate.status = status_update.status
    db.commit()
    db.refresh(candidate)

    # --- МАГИЯ: ОТПРАВКА УВЕДОМЛЕНИЯ ---
    # Если статус стал "interview", шлем поздравление
    if status_update.status == "interview" and candidate.telegram_id:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if token:
            msg = (
                f"🎉 <b>Поздравляем, {candidate.first_name}!</b>\n\n"
                f"Ваше резюме понравилось нашему AI и рекрутеру.\n"
                f"Мы приглашаем вас на интервью! Скоро с вами свяжутся для уточнения времени."
            )
            # Отправляем запрос напрямую в Telegram API
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            async with httpx.AsyncClient() as client:
                try:
                    await client.post(url, json={
                        "chat_id": candidate.telegram_id,
                        "text": msg,
                        "parse_mode": "HTML"
                    })
                    print(f"Уведомление отправлено пользователю {candidate.telegram_id}")
                except Exception as e:
                    print(f"Ошибка отправки уведомления: {e}")

    return candidate

# Добавим ручку для получения кандидатов (чтобы видеть их на фронте)
@app.get("/candidates/", response_model=List[CandidateResponse])
def read_candidates(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    candidates = db.query(Candidate).offset(skip).limit(limit).all()
    return candidates