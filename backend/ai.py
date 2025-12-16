import json
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

# Проверка ключа при старте
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("!!! ОШИБКА: Не найден OPENAI_API_KEY в .env !!!")

client = OpenAI(api_key=api_key)

def analyze_resume_with_gpt(resume_text: str, vacancy_description: str):
    print("--- НАЧАЛО AI АНАЛИЗА ---")
    print(f"Длина резюме: {len(resume_text)} символов")
    
    prompt = f"""
    Ты профессиональный HR-рекрутер. Твоя задача - оценить резюме кандидата относительно вакансии.
    
    ВАКАНСИЯ:
    {vacancy_description}
    
    РЕЗЮМЕ:
    {resume_text}
    
    Проанализируй и верни ответ ТОЛЬКО в формате JSON:
    {{
        "score": <число от 0 до 100>,
        "summary": "<краткое резюме на русском>",
        "pros": ["<плюс 1>", "<плюс 2>"],
        "cons": ["<минус 1>", "<минус 2>"]
    }}
    """

    try:
        print("Отправляем запрос в OpenAI...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful HR assistant. Output JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        print("Ответ от OpenAI получен!")
        print(f"Raw content: {content[:100]}...") # Покажем начало ответа
        
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
        
    except Exception as e:
        print(f"!!! AI Error: {e}")
        # Возвращаем заглушку, чтобы бот не молчал
        return {
            "score": 10,
            "summary": f"Ошибка AI анализа: {str(e)}",
            "pros": [],
            "cons": ["Ошибка сервиса"]
        }
    
def generate_vacancy_description(title: str, requirements: str, salary: str = "", city: str = "", experience: str = ""):
    prompt = f"""
    Ты профессиональный HR. Напиши описание вакансии.
    
    Должность: {title}
    Требования: {requirements}
    Зарплата: {salary}
    Город: {city}
    Опыт: {experience}
    
    Верни ответ ТОЛЬКО в формате JSON:
    {{
        "description": "<вводная часть, чем заниматься, 2-3 предложения. Упомяни город и зарплату, если они достойные>",
        "requirements": "<список требований, bullet points>",
        "conditions": "<список условий (офис/удаленка, плюшки)>"
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful HR assistant. Output JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        content = response.choices[0].message.content
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except Exception as e:
        print(f"AI Error: {e}")
        return {
            "description": "Описание не сгенерировано.",
            "requirements": requirements,
            "conditions": "Стандартные условия."
        }