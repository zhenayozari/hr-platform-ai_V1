from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from ..database import get_db
from ..models import Company, User, PipelineStage, EmailTemplate, Candidate
from ..auth.dependencies import get_current_user, get_current_active_admin
from ..auth.utils import get_password_hash

router = APIRouter(prefix="/settings", tags=["Настройки"])

# ============================================================
# СХЕМЫ ДАННЫХ
# ============================================================

# --- Компания ---
class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None

class CompanyResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# --- Пользователи ---
class UserCreate(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str = ""
    role: str = "recruiter"

class UserRoleUpdate(BaseModel):
    role: str

class UserInCompany(BaseModel):
    id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    is_active: bool
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# --- Pipeline (Этапы воронки) ---
class PipelineStageCreate(BaseModel):
    key: str
    label: str
    color: str = "#3B82F6"
    is_final: bool = False

class PipelineStageUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None

class PipelineStageResponse(BaseModel):
    id: int
    key: str
    label: str
    color: str
    order: int
    is_active: bool
    is_final: bool
    
    class Config:
        from_attributes = True

class PipelineReorderRequest(BaseModel):
    stage_ids: List[int]

# --- Email Templates (Шаблоны писем) ---
class EmailTemplateCreate(BaseModel):
    type: str
    name: str
    subject: str
    body: str

class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    is_active: Optional[bool] = None

class EmailTemplateResponse(BaseModel):
    id: int
    type: str
    name: str
    subject: str
    body: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def create_default_pipeline_stages(db: Session, company_id: int) -> List[PipelineStage]:
    """Создаёт стандартные этапы воронки для новой компании."""
    default_stages = [
        {"key": "new", "label": "Новый", "color": "#3B82F6", "order": 0, "is_final": False},
        {"key": "screening", "label": "Скрининг", "color": "#8B5CF6", "order": 1, "is_final": False},
        {"key": "interview", "label": "Интервью", "color": "#F59E0B", "order": 2, "is_final": False},
        {"key": "offer", "label": "Оффер", "color": "#F97316", "order": 3, "is_final": False},
        {"key": "hired", "label": "Нанят", "color": "#10B981", "order": 4, "is_final": True},
        {"key": "rejected", "label": "Отказ", "color": "#EF4444", "order": 5, "is_final": True},
    ]
    
    stages = []
    for stage_data in default_stages:
        stage = PipelineStage(company_id=company_id, **stage_data)
        db.add(stage)
        stages.append(stage)
    
    db.commit()
    for stage in stages:
        db.refresh(stage)
    
    return stages


def create_default_email_templates(db: Session, company_id: int) -> List[EmailTemplate]:
    """Создаёт стандартные шаблоны писем для новой компании."""
    defaults = [
        {
            "type": "invitation",
            "name": "Приглашение на интервью",
            "subject": "Приглашение на собеседование — {vacancy_title}",
            "body": """Здравствуйте, {first_name}!

Благодарим вас за интерес к позиции {vacancy_title} в компании {company_name}.

Мы внимательно изучили ваше резюме и хотели бы пригласить вас на собеседование.

Пожалуйста, свяжитесь с нами для согласования удобного времени.

С уважением,
HR-команда {company_name}"""
        },
        {
            "type": "rejection",
            "name": "Отказ",
            "subject": "Ответ по вашей заявке — {vacancy_title}",
            "body": """Здравствуйте, {first_name}!

Благодарим вас за интерес к позиции {vacancy_title} и время, уделённое компании {company_name}.

К сожалению, мы приняли решение продолжить рассмотрение других кандидатов на данную позицию.

Мы сохранили ваше резюме и обязательно свяжемся с вами, если появится подходящая вакансия.

Желаем успехов в поиске работы!

С уважением,
HR-команда {company_name}"""
        },
        {
            "type": "offer",
            "name": "Предложение о работе",
            "subject": "Предложение о работе — {vacancy_title}",
            "body": """Здравствуйте, {first_name}!

Мы рады сообщить, что по итогам собеседований приняли решение сделать вам предложение о работе на позицию {vacancy_title}!

Мы готовы обсудить детали оффера в удобное для вас время.

Ждём вашего ответа!

С уважением,
HR-команда {company_name}"""
        }
    ]
    
    templates = []
    for tpl_data in defaults:
        template = EmailTemplate(company_id=company_id, **tpl_data)
        db.add(template)
        templates.append(template)
    
    db.commit()
    for template in templates:
        db.refresh(template)
    
    return templates

# ============================================================
# ЭНДПОИНТЫ: КОМПАНИЯ
# ============================================================

@router.get("/company", response_model=CompanyResponse)
def get_company_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Получить профиль компании"""
    return db.query(Company).filter(Company.id == current_user.company_id).first()


@router.patch("/company", response_model=CompanyResponse)
def update_company_profile(
    data: CompanyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Обновить профиль компании (только админ)"""
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    
    for field, value in data.dict(exclude_unset=True).items():
        setattr(company, field, value)
    
    db.commit()
    db.refresh(company)
    return company

# ============================================================
# ЭНДПОИНТЫ: ПОЛЬЗОВАТЕЛИ
# ============================================================

@router.get("/users", response_model=List[UserInCompany])
def get_company_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Получить список пользователей компании"""
    return db.query(User).filter(User.company_id == current_user.company_id).all()


@router.post("/users", response_model=UserInCompany)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Добавить пользователя в компанию (только админ)"""
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email уже используется")
    
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role,
        company_id=current_user.company_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/role", response_model=UserInCompany)
def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Изменить роль пользователя (только админ)"""
    user = db.query(User).filter(
        User.id == user_id,
        User.company_id == current_user.company_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя изменить свою роль")
    
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Деактивировать пользователя (только админ)"""
    user = db.query(User).filter(
        User.id == user_id,
        User.company_id == current_user.company_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить себя")
    
    user.is_active = False
    db.commit()
    return {"status": "ok", "message": "Пользователь деактивирован"}

# ============================================================
# ЭНДПОИНТЫ: PIPELINE (ЭТАПЫ ВОРОНКИ)
# ============================================================

@router.get("/pipeline", response_model=List[PipelineStageResponse])
def get_pipeline_stages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Получить все этапы воронки. Если нет — создаёт дефолтные."""
    stages = db.query(PipelineStage).filter(
        PipelineStage.company_id == current_user.company_id
    ).order_by(PipelineStage.order).all()
    
    if not stages:
        stages = create_default_pipeline_stages(db, current_user.company_id)
    
    return stages


@router.post("/pipeline", response_model=PipelineStageResponse)
def create_pipeline_stage(
    data: PipelineStageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Создать новый этап воронки (только админ)"""
    # Проверяем уникальность key
    existing = db.query(PipelineStage).filter(
        PipelineStage.company_id == current_user.company_id,
        PipelineStage.key == data.key
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"Этап с ключом '{data.key}' уже существует")
    
    # Определяем order — ставим в конец (перед финальными)
    max_order_stage = db.query(PipelineStage).filter(
        PipelineStage.company_id == current_user.company_id,
        PipelineStage.is_final == False
    ).order_by(PipelineStage.order.desc()).first()
    
    new_order = (max_order_stage.order + 1) if max_order_stage else 0
    
    stage = PipelineStage(
        company_id=current_user.company_id,
        key=data.key,
        label=data.label,
        color=data.color,
        order=new_order,
        is_final=data.is_final,
        is_active=True
    )
    
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage


@router.patch("/pipeline/{stage_id}", response_model=PipelineStageResponse)
def update_pipeline_stage(
    stage_id: int,
    data: PipelineStageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Обновить этап воронки (только админ)"""
    stage = db.query(PipelineStage).filter(
        PipelineStage.id == stage_id,
        PipelineStage.company_id == current_user.company_id
    ).first()
    
    if not stage:
        raise HTTPException(status_code=404, detail="Этап не найден")
    
    # Финальные этапы нельзя деактивировать
    if stage.is_final and data.is_active == False:
        raise HTTPException(status_code=400, detail="Нельзя скрыть финальный этап")
    
    if data.label is not None:
        stage.label = data.label
    if data.color is not None:
        stage.color = data.color
    if data.is_active is not None:
        stage.is_active = data.is_active
    
    db.commit()
    db.refresh(stage)
    return stage


@router.post("/pipeline/reorder")
def reorder_pipeline_stages(
    data: PipelineReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Изменить порядок этапов (только админ)"""
    for index, stage_id in enumerate(data.stage_ids):
        stage = db.query(PipelineStage).filter(
            PipelineStage.id == stage_id,
            PipelineStage.company_id == current_user.company_id
        ).first()
        
        if stage:
            stage.order = index
    
    db.commit()
    return {"status": "ok", "message": "Порядок обновлён"}


@router.delete("/pipeline/{stage_id}")
def delete_pipeline_stage(
    stage_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Удалить этап воронки (только админ)"""
    stage = db.query(PipelineStage).filter(
        PipelineStage.id == stage_id,
        PipelineStage.company_id == current_user.company_id
    ).first()
    
    if not stage:
        raise HTTPException(status_code=404, detail="Этап не найден")
    
    if stage.is_final:
        raise HTTPException(status_code=400, detail="Нельзя удалить финальный этап")
    
    # Проверяем, есть ли кандидаты на этом этапе
    candidates_count = db.query(Candidate).filter(
        Candidate.company_id == current_user.company_id,
        Candidate.status == stage.key
    ).count()
    
    if candidates_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Нельзя удалить: на этапе {candidates_count} кандидат(ов)"
        )
    
    db.delete(stage)
    db.commit()
    return {"status": "ok", "message": "Этап удалён"}

# ============================================================
# ЭНДПОИНТЫ: EMAIL TEMPLATES (ШАБЛОНЫ ПИСЕМ)
# ============================================================

@router.get("/email-templates", response_model=List[EmailTemplateResponse])
def get_email_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Получить все шаблоны писем. Если нет — создаёт дефолтные."""
    templates = db.query(EmailTemplate).filter(
        EmailTemplate.company_id == current_user.company_id
    ).order_by(EmailTemplate.created_at).all()
    
    if not templates:
        templates = create_default_email_templates(db, current_user.company_id)
    
    return templates


@router.get("/email-templates/{template_id}", response_model=EmailTemplateResponse)
def get_email_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Получить один шаблон по ID"""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.id == template_id,
        EmailTemplate.company_id == current_user.company_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    
    return template


@router.post("/email-templates", response_model=EmailTemplateResponse)
def create_email_template(
    data: EmailTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Создать новый шаблон письма (только админ)"""
    template = EmailTemplate(
        company_id=current_user.company_id,
        type=data.type,
        name=data.name,
        subject=data.subject,
        body=data.body,
        is_active=True
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.patch("/email-templates/{template_id}", response_model=EmailTemplateResponse)
def update_email_template(
    template_id: int,
    data: EmailTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Обновить шаблон письма (только админ)"""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.id == template_id,
        EmailTemplate.company_id == current_user.company_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    
    if data.name is not None:
        template.name = data.name
    if data.subject is not None:
        template.subject = data.subject
    if data.body is not None:
        template.body = data.body
    if data.is_active is not None:
        template.is_active = data.is_active
    
    db.commit()
    db.refresh(template)
    return template


@router.delete("/email-templates/{template_id}")
def delete_email_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """Удалить шаблон письма (только админ)"""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.id == template_id,
        EmailTemplate.company_id == current_user.company_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    
    db.delete(template)
    db.commit()
    return {"status": "ok", "message": "Шаблон удалён"}


@router.post("/email-templates/{template_id}/preview")
def preview_email_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Предпросмотр шаблона с тестовыми данными"""
    template = db.query(EmailTemplate).filter(
        EmailTemplate.id == template_id,
        EmailTemplate.company_id == current_user.company_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    
    # Тестовые данные
    test_data = {
        "first_name": "Иван",
        "last_name": "Петров",
        "vacancy_title": "Python Developer",
        "company_name": current_user.company.name
    }
    
    # Подставляем переменные
    subject = template.subject
    body = template.body
    
    for key, value in test_data.items():
        subject = subject.replace(f"{{{key}}}", value)
        body = body.replace(f"{{{key}}}", value)
    
    return {
        "subject": subject,
        "body": body,
        "test_data": test_data
    }