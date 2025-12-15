from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from .utils import decode_token

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    
    # Декодируем токен
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен или срок действия истек",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Извлекаем user_id
    try:
        user_id = int(payload.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректный ID пользователя",
        )

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен не содержит ID пользователя",
        )
    
    # Находим пользователя
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован",
        )
    
    return user

# --- ФУНКЦИИ ПРОВЕРКИ РОЛЕЙ (ИХ НЕ ХВАТАЛО) ---

async def get_current_active_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Проверяет, что пользователь — администратор"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав. Требуется роль admin.",
        )
    return current_user

async def get_current_recruiter_or_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Проверяет, что пользователь — рекрутер или админ"""
    if current_user.role not in ["admin", "recruiter"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав.",
        )
    return current_user

# --- ПРОВЕРКА ДОСТУПА К КОМПАНИИ ---

def check_company_access(obj, current_user: User, obj_name: str = "Объект"):
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{obj_name} не найден"
        )
    
    if obj.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Нет доступа к этому объекту"
        )
    return obj