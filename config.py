# config.py - поместите этот файл в C:\Users\АДМИН\ProjectRazMedBot\
import os
from typing import Optional
from pydantic import BaseModel, validator
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


class BotConfig(BaseModel):
    """Конфигурация бота через Pydantic"""

    # Обязательные параметры (из .env)
    BOT_TOKEN: str
    ADMIN_ID: int

    # Настройки файлов и документов
    MAX_DOCUMENTS: int = 10
    MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 20 MB

    # Настройки платежей
    PROVIDER_TOKEN: Optional[str] = None
    PAYMENT_TEST_MODE: bool = True
    TEST_PAYMENT_PRICE: int = 1

    # Пути и база данных
    DATABASE_URL: str = "sqlite:///orders.db"
    BACKUP_DIR: str = "backups"

    # Данные самозанятого
    SELF_EMPLOYED_NAME: str = "Семёнычев Никита Сергеевич"
    SELF_EMPLOYED_INN: str = "164514339030"
    SUPPORT_CHANNEL: str = "https://t.me/ponyatmed"

    # Настройки уточнений
    CLARIFICATION_TIME_LIMIT_HOURS: int = 24

    # Реферальная система
    REFERRER_BONUS_PERCENT: int = 10  # 10% приглашающему
    REFERRED_DISCOUNT_PERCENT: int = 5  # 5% приглашенному

    # Дополнительные настройки
    LOG_LEVEL: str = "INFO"
    DATABASE_BACKUP_COUNT: int = 10
    PAYMENT_TIMEOUT_MINUTES: int = 15
    DEFAULT_SERVICE_PRICE: int = 490

    @validator('BOT_TOKEN')
    def validate_token(cls, v):
        if not v:
            raise ValueError("BOT_TOKEN не может быть пустым")
        return v

    @validator('ADMIN_ID')
    def validate_admin_id(cls, v):
        if v == 0:
            raise ValueError("ADMIN_ID не может быть 0")
        return v


# Создаем глобальный объект конфигурации
try:
    config = BotConfig(
        BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
        ADMIN_ID=int(os.getenv("ADMIN_ID", 0)),
        PROVIDER_TOKEN=os.getenv("PROVIDER_TOKEN")
    )

    # Проверяем основные параметры
    if not config.BOT_TOKEN:
        print("⚠️ ВНИМАНИЕ: BOT_TOKEN не установлен!")
        print("Создайте файл .env с BOT_TOKEN=ваш_токен")

    if config.ADMIN_ID == 0:
        print("⚠️ ВНИМАНИЕ: ADMIN_ID не установлен!")
        print("Добавьте ADMIN_ID=ваш_id в файл .env")

except Exception as e:
    print(f"❌ Ошибка загрузки конфигурации: {e}")
    print("Проверьте файл .env или установите переменные окружения")
    raise