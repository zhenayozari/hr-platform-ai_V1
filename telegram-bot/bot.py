import logging
import os
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = "http://127.0.0.1:8000"

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("--- Команда /start ---")
    await update.message.reply_text(
        "Привет! Я HR-ассистент. Я помогу тебе подать заявку на вакансию.\n"
        "Используй /vacancies чтобы посмотреть список открытых позиций."
    )

async def get_vacancies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("--- Запрос вакансий ---")
    # trust_env=False важно для работы на Windows без прокси проблем
    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            response = await client.get(f"{API_URL}/vacancies/")
            vacancies = response.json()
            
            if not vacancies:
                await update.message.reply_text("Пока нет открытых вакансий.")
                return

            keyboard = []
            for v in vacancies:
                keyboard.append([InlineKeyboardButton(v['title'], callback_data=f"apply_{v['id']}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Выберите вакансию для отклика:", reply_markup=reply_markup)
            
        except Exception as e:
            logging.error(f"Error connecting to API: {e}")
            await update.message.reply_text("Ошибка соединения с сервером HR платформы.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    print(f"--- Нажата кнопка: {data} ---")
    
    if data.startswith("apply_"):
        vacancy_id = data.split("_")[1]
        context.user_data['applying_for'] = vacancy_id
        print(f"Пользователь выбрал вакансию ID: {vacancy_id}")
        
        await query.edit_message_text(
            text=f"Отлично! Вы выбрали вакансию ID {vacancy_id}.\n"
                 f"Теперь просто пришлите мне ваше резюме **текстовым сообщением** (скопируйте и вставьте текст)."
        )

async def handle_text_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("!!! ХЕНДЛЕР ТЕКСТА СРАБОТАЛ !!!")
    user_text = update.message.text
    print(f"Получен текст длиной: {len(user_text)} символов")

    # Проверяем, выбрал ли пользователь вакансию
    if 'applying_for' not in context.user_data:
        print("Ошибка: Вакансия не выбрана")
        await update.message.reply_text("Сначала выберите вакансию через команду /vacancies")
        return

    vacancy_id = context.user_data['applying_for']
    user = update.message.from_user

    await update.message.reply_text("⏳ Принято! Искусственный интеллект анализирует ваше резюме... Это займет пару секунд.")

    # Формируем данные
    payload = {
        "vacancy_id": int(vacancy_id),
        "first_name": user.first_name,
        "last_name": user.last_name or "",
        "username": str(user.id), # <--- Шлем цифровой ID, чтобы бот мог ответить
        "resume_text": user_text
    }

    print("Отправляем данные на Бэкенд...")
    async with httpx.AsyncClient(trust_env=False, timeout=60.0) as client:
        try:
            response = await client.post(f"{API_URL}/candidates/apply", json=payload)
            print(f"Ответ сервера: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                score = data['ai_score']
                summary = data['ai_summary']
                
                msg = (
                    f"✅ **Анализ завершен!**\n\n"
                    f"📊 **Релевантность:** {score}/100\n"
                    f"📝 **Вердикт AI:** {summary}\n\n"
                    f"Ваше резюме сохранено в базе."
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
                
                # Очищаем выбор
                del context.user_data['applying_for']
            else:
                print(f"Ошибка API: {response.text}")
                await update.message.reply_text(f"Ошибка сервера: {response.text}")
                
        except Exception as e:
            logging.error(f"Error in handle_text_resume: {e}")
            await update.message.reply_text("Произошла ошибка при обработке резюме.")

if __name__ == '__main__':
    # Проверяем токен
    if not TOKEN:
        print("ОШИБКА: Токен не найден! Проверь .env")
        exit()

    application = ApplicationBuilder().token(TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('vacancies', get_vacancies))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # ВАЖНО: Обработчик текста должен быть зарегистрирован!
    # filters.TEXT & (~filters.COMMAND) означает "любой текст, который не является командой"
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_resume))
    
    print("Бот запущен и готов к работе...")
    application.run_polling()