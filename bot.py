# bot.py - Главный файл запуска (для aiogram 3.x)
import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

# Импорт конфигурации
from config import config

# Добавляем корневую директорию в PYTHONPATH для корректных импортов
sys.path.append(str(Path(__file__).parent))

# Создаем необходимые директории
backup_dir = Path(__file__).parent / "backups"
logs_dir = Path(__file__).parent / "logs"
backup_dir.mkdir(exist_ok=True)
logs_dir.mkdir(exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / "bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Инициализация базы данных
from database import db

# Инициализация бота с настройками по умолчанию
# В aiogram 3.x DefaultBotProperties может не быть во всех версиях
# Используем простой вариант
bot = Bot(token=config.BOT_TOKEN, parse_mode=ParseMode.HTML)

# Инициализация диспетчера
storage = MemoryStorage()
dp = Dispatcher(storage=storage, name="main_dispatcher")


async def include_routers():
    """Регистрация всех роутеров"""
    try:
        # Импортируем роутеры
        from handlers.common import router as common_router
        from handlers.user import router as user_router
        from handlers.payment import router as payment_router
        from handlers.admin import router as admin_router

        # Регистрируем роутеры
        dp.include_router(common_router)
        dp.include_router(user_router)
        dp.include_router(payment_router)
        dp.include_router(admin_router)

        logger.info("Все роутеры успешно зарегистрированы")
        return True

    except ImportError as e:
        logger.error(f"Ошибка импорта роутеров: {e}")
        raise e
    except Exception as e:
        logger.error(f"Ошибка регистрации роутеров: {e}")
        raise e


async def setup_bot_commands():
    """Настройка команд бота для меню"""
    from aiogram.types import BotCommand, BotCommandScopeDefault

    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь и команды"),
        BotCommand(command="my_orders", description="Мои заказы"),
        BotCommand(command="status", description="Статус заказа"),
        BotCommand(command="about", description="О сервисе"),
        BotCommand(command="support", description="Поддержка"),
        BotCommand(command="cancel", description="Отменить действие"),
    ]

    try:
        await bot.set_my_commands(commands=commands, scope=BotCommandScopeDefault())
        logger.info("Команды бота успешно настроены")
    except Exception as e:
        logger.error(f"Ошибка настройки команд: {e}")


async def on_startup():
    """Действия при запуске бота"""
    logger.info("=" * 50)
    logger.info(f"Запуск медицинского бота RazMedBot")
    logger.info(f"Токен: {config.BOT_TOKEN[:15]}...")
    logger.info(f"Режим оплаты: {'ТЕСТОВЫЙ' if config.PAYMENT_TEST_MODE else 'РЕАЛЬНЫЙ'}")
    logger.info(f"Макс. документов: {config.MAX_DOCUMENTS}")
    logger.info(f"Размер файла: {config.MAX_FILE_SIZE / (1024 * 1024)} МБ")
    logger.info(f"Админ ID: {config.ADMIN_ID}")
    logger.info("=" * 50)

    # Проверяем токен
    try:
        bot_info = await bot.get_me()
        logger.info(f"Бот авторизован как: @{bot_info.username} (ID: {bot_info.id})")
    except Exception as e:
        logger.error(f"Ошибка авторизации бота: {e}")
        raise

    # Настраиваем команды
    await setup_bot_commands()

    # Создаем резервную копию БД
    try:
        if db.backup():
            logger.info("Резервная копия БД создана при запуске")
    except Exception as e:
        logger.warning(f"Не удалось создать бэкап при запуске: {e}")

    # Отправляем уведомление админу
    try:
        await bot.send_message(
            chat_id=config.ADMIN_ID,
            text=f"✅ <b>Бот запущен!</b>\n\n"
                 f"Время: {asyncio.get_event_loop().time()}\n"
                 f"Статус: Работает\n"
                 f"Режим оплаты: {'🟡 ТЕСТОВЫЙ' if config.PAYMENT_TEST_MODE else '🟢 РЕАЛЬНЫЙ'}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить админа о запуске: {e}")


async def on_shutdown():
    """Действия при остановке бота"""
    logger.info("Остановка бота...")

    # Закрываем соединение с БД
    try:
        db.conn.close()
        logger.info("Соединение с БД закрыто")
    except Exception as e:
        logger.error(f"Ошибка закрытия БД: {e}")

    # Отправляем уведомление админу
    try:
        await bot.send_message(
            chat_id=config.ADMIN_ID,
            text="🛑 <b>Бот остановлен</b>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить админа об остановке: {e}")


async def main():
    """Главная функция запуска бота"""
    try:
        # Действия при запуске
        await on_startup()

        # Регистрация роутеров
        await include_routers()

        logger.info("Бот готов к работе. Ожидание сообщений...")

        # Запуск поллинга
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {e}", exc_info=True)

        # Уведомляем админа о критической ошибке
        try:
            await bot.send_message(
                chat_id=config.ADMIN_ID,
                text=f"🚨 <b>Критическая ошибка при запуске бота!</b>\n\n"
                     f"<code>{str(e)[:500]}</code>",
                parse_mode=ParseMode.HTML
            )
        except:
            pass

        raise

    finally:
        # Действия при остановке
        await on_shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"Необработанное исключение: {e}", exc_info=True)
        sys.exit(1)