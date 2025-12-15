from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from .utils import decode_token

# Схема авторизации через Bearer token
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    print(f"DEBUG: Получен токен: {token[:10]}...") # Покажем начало токена
    
    # Декодируем токен
    payload = decode_token(token)
    if payload is None:
        print("DEBUG: Ошибка декодирования токена (payload is None)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    print(f"DEBUG: Payload: {payload}")

    # Извлекаем user_id
    user_id: int = payload.get("sub")
    if user_id is None:
        print("DEBUG: В токене нет user_id")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен не содержит информации о пользователе",
        )
    
    # Находим пользователя
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        print(f"DEBUG: Пользователь с ID {user_id} не найден в базе")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )
    
    if not user.is_active:
        print("DEBUG: Пользователь не активен")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован",
        )
    
    print(f"DEBUG: Успешная авторизация: {user.email}")
    return user

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
            detail="Недостаточно прав. Требуется роль recruiter или admin.",
        )
    return current_user

def check_company_access(obj, current_user: User, obj_name: str = "Объект"):
    """
    Проверяет, что объект принадлежит компании пользователя.
    """
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