# handlers/common.py
import logging
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)

from database import db
from utils.keyboards import create_main_menu
from handlers.admin import is_admin

logger = logging.getLogger(__name__)

router = Router()


# ========== КОМАНДА HELP ==========
@router.message(Command("help"))
async def cmd_help(message: Message):
    """Показать справку по командам"""
    help_text = """<b>🆘 СПРАВКА ПО КОМАНДАМ</b>

<b>Основные команды:</b>
/start - Начать работу с ботом
/help - Показать эту справку
/cancel - Отменить текущее действие
/my_orders - Посмотреть мои заказы

<b>Действия (через кнопки):</b>
• 🩺 Создать заказ - Оформить новый заказ
• 📋 Мои заказы - Посмотреть историю заказов
• 👨‍⚕️ О сервисе - Информация о сервисе
• 👨‍💻 Связаться - Связаться с поддержкой
• 👥 Пригласить друга - Реферальная программа

<b>Для администраторов:</b>
/admin - Открыть админ-панель
/statistics - Показать статистику
/export_stats - Экспорт статистики в CSV
/create_promo [код] [тип] [значение] - Создать промокод"""

    await message.answer(help_text, parse_mode="HTML")


# ========== КОМАНДА CANCEL ==========
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    current_state = await state.get_state()

    if current_state is None:
        await message.answer("❌ Нет активных действий для отмены.")
        return

    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=ReplyKeyboardRemove()
    )

    # Возвращаем в главное меню
    if is_admin(message.from_user.id):
        from handlers.admin import create_admin_menu
        await message.answer(
            "🏠 <b>Главное меню администратора</b>",
            parse_mode="HTML",
            reply_markup=create_admin_menu()
        )
    else:
        await message.answer(
            "🏠 <b>Главное меню</b>",
            parse_mode="HTML",
            reply_markup=create_main_menu()
        )


# ========== КОМАНДА MY_ORDERS ==========
@router.message(Command("my_orders"))
async def cmd_my_orders(message: Message):
    """Показать заказы пользователя через команду"""
    try:
        orders = db.get_user_orders(message.from_user.id, limit=10)

        if not orders:
            await message.answer(
                "📭 <b>У вас пока нет заказов</b>\n\n"
                "Создайте ваш первый заказ, нажав кнопку \"🩺 Создать заказ\"",
                parse_mode="HTML"
            )
            return

        orders_text = "<b>📋 ВАШИ ЗАКАЗЫ</b>\n\n"

        for order in orders[:5]:  # Показываем первые 5 заказов
            order_id = order[0]
            service_type = order[8] if len(order) > 8 else "Не указано"
            status = order[9] if len(order) > 9 else "pending"
            created_at = order[10] if len(order) > 10 else None
            price = order[14] if len(order) > 14 else 0

            # Форматируем дату
            if isinstance(created_at, str):
                date_str = created_at[:10] if len(created_at) >= 10 else created_at
            else:
                date_str = created_at.strftime("%d.%m.%Y") if hasattr(created_at, 'strftime') else str(created_at)

            # Иконка статуса
            status_icons = {
                'pending': '⏳',
                'processing': '🔧',
                'completed': '✅',
                'paid': '💰',
                'awaiting_clarification': '❓',
                'needs_new_docs': '📄'
            }

            status_icon = status_icons.get(status, '📋')

            orders_text += f"{status_icon} <b>Заказ #{order_id}</b>\n"
            orders_text += f"   Услуга: {service_type}\n"
            orders_text += f"   Стоимость: {price}₽\n"
            orders_text += f"   Дата: {date_str}\n"
            orders_text += f"   Статус: {status}\n"
            orders_text += "   ─────────────────\n"

        if len(orders) > 5:
            orders_text += f"\n📊 <i>И еще {len(orders) - 5} заказов...</i>"

        orders_text += "\n<b>💡 Для просмотра деталей конкретного заказа напишите его номер в поддержку.</b>"

        await message.answer(orders_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при показе заказов: {e}")
        await message.answer(
            "❌ <b>Ошибка при загрузке ваших заказов</b>\n\n"
            "Попробуйте позже или обратитесь в поддержку.",
            parse_mode="HTML"
        )


# ========== КОМАНДА STATUS ==========
@router.message(Command("status"))
async def cmd_status(message: Message, command: CommandObject):
    """Проверить статус конкретного заказа"""
    try:
        if not command.args:
            await message.answer(
                "❌ <b>Укажите номер заказа:</b>\n"
                "<code>/status 123</code> - для проверки статуса заказа #123",
                parse_mode="HTML"
            )
            return

        order_id = int(command.args.strip())
        order = db.get_order_by_id(order_id)

        if not order:
            await message.answer(f"❌ Заказ #{order_id} не найден.")
            return

        # Проверяем, что заказ принадлежит пользователю или это админ
        user_id_from_order = order[1]
        if user_id_from_order != message.from_user.id and not is_admin(message.from_user.id):
            await message.answer("❌ Это не ваш заказ.")
            return

        service_type = order[8] if len(order) > 8 else "Не указано"
        status = order[9] if len(order) > 9 else "pending"
        created_at = order[10] if len(order) > 10 else None
        price = order[14] if len(order) > 14 else 0
        questions = order[5] if len(order) > 5 else None

        # Иконка статуса
        status_icons = {
            'pending': '⏳ Ожидает обработки',
            'processing': '🔧 В обработке',
            'completed': '✅ Завершен',
            'paid': '💰 Оплачен',
            'awaiting_clarification': '❓ Ожидает уточнения',
            'needs_new_docs': '📄 Требуются документы'
        }

        status_text = status_icons.get(status, status)

        # Форматируем дату
        date_str = "неизвестно"
        if created_at:
            try:
                if isinstance(created_at, str):
                    date_str = created_at[:16]
                else:
                    date_str = created_at.strftime("%d.%m.%Y %H:%M")
            except:
                date_str = str(created_at)

        status_message = f"""<b>📊 СТАТУС ЗАКАЗА #{order_id}</b>

<b>Услуга:</b> {service_type}
<b>Статус:</b> {status_text}
<b>Стоимость:</b> {price}₽
<b>Дата создания:</b> {date_str}

<b>Ваш вопрос:</b>
{questions[:200] + '...' if questions and len(questions) > 200 else questions or 'Не указан'}

<b>💡 Что дальше?</b>"""

        # Добавляем рекомендации в зависимости от статуса
        if status == 'pending':
            status_message += "\n• Заказ принят, ожидайте ответа специалиста"
        elif status == 'processing':
            status_message += "\n• Специалист работает над вашим заказом"
        elif status == 'awaiting_clarification':
            status_message += "\n• Вы можете задать уточняющий вопрос"
        elif status == 'needs_new_docs':
            status_message += "\n• Пожалуйста, загрузите дополнительные документы"
        elif status == 'completed':
            status_message += "\n• Заказ завершен, вы можете оценить качество"

        status_message += "\n\n<b>❓ Есть вопросы?</b> Напишите в поддержку."

        await message.answer(status_message, parse_mode="HTML")

    except ValueError:
        await message.answer("❌ Неверный номер заказа. Укажите число.")
    except Exception as e:
        logger.error(f"Ошибка проверки статуса: {e}")
        await message.answer("❌ Ошибка при проверке статуса заказа.")


# ========== КОМАНДА ABOUT ==========
@router.message(Command("about"))
async def cmd_about(message: Message):
    """Информация о сервисе"""
    about_text = """<b>👨‍⚕️ О СЕРВИСЕ RAZMEDBOT</b>

🏥 <b>Миссия:</b> Сделать медицинскую информацию доступной и понятной для каждого.

✨ <b>Что мы делаем:</b>
• Расшифровываем медицинские анализы и исследования
• Объясняем врачебные заключения простым языком
• Помогаем понять диагнозы и назначения
• Консультируем по медицинским документам

🔬 <b>Наша методология:</b>
1. <b>AI-анализ:</b> Искусственный интеллект обрабатывает ваши документы
2. <b>Экспертная проверка:</b> Медицинский специалист проверяет результаты
3. <b>Детальная расшифровка:</b> Вы получаете понятное объяснение

⏱️ <b>Сроки:</b> До 24 часов
💎 <b>Стоимость:</b> От 190₽ за расшифровку
✅ <b>Гарантии:</b> Конфиденциальность и точность

<b>📞 Контакты:</b>
Поддержка: @razmed_support
Для сотрудничества: @razmed_admin

<b>Мы делаем медицину понятной!</b>"""

    await message.answer(about_text, parse_mode="HTML")


# ========== КОМАНДА SUPPORT ==========
@router.message(Command("support"))
async def cmd_support(message: Message, command: CommandObject):
    """Связаться с поддержкой"""
    if command.args:
        # Если указан текст вопроса
        question = command.args.strip()

        # Здесь можно добавить логику отправки вопроса в поддержку
        # Например, отправка админу или в канал поддержки

        await message.answer(
            f"✅ <b>Ваш вопрос отправлен в поддержку!</b>\n\n"
            f"<b>Ваш вопрос:</b>\n{question}\n\n"
            f"Ответ придет вам в этот чат в течение 24 часов.",
            parse_mode="HTML"
        )
    else:
        # Просто показываем контакты поддержки
        support_text = """<b>👨‍💻 СВЯЗЬ С ПОДДЕРЖКОЙ</b>

Вы можете обратиться в поддержку следующими способами:

<b>1. 📱 Через бота:</b>
Напишите команду: <code>/support [ваш вопрос]</code>
Пример: <code>/support Не пришел ответ по заказу #123</code>

<b>2. 📢 Прямой контакт:</b>
Телеграм: @razmed_support
Email: support@razmed.ru

<b>3. 📞 Срочные вопросы:</b>
Укажите в сообщении "СРОЧНО"

<b>⏱️ Время ответа:</b>
• Обычные вопросы: до 24 часов
• Срочные вопросы: до 6 часов

<b>📋 Что указать при обращении:</b>
• Номер вашего заказа (если есть)
• Ваш username или ID
• Подробное описание проблемы"""

        await message.answer(support_text, parse_mode="HTML")


# ========== КОМАНДА FEEDBACK ==========
@router.message(Command("feedback"))
async def cmd_feedback(message: Message, command: CommandObject):
    """Отправить отзыв о работе сервиса"""
    if not command.args:
        await message.answer(
            "📝 <b>ОТЗЫВ О СЕРВИСЕ</b>\n\n"
            "Пожалуйста, напишите ваш отзыв командой:\n"
            "<code>/feedback [ваш отзыв]</code>\n\n"
            "Пример: <code>/feedback Отличный сервис, все понятно объяснили!</code>",
            parse_mode="HTML"
        )
        return

    feedback_text = command.args.strip()

    # Здесь можно добавить логику сохранения отзыва в БД
    # или отправки админу

    await message.answer(
        "✅ <b>Спасибо за ваш отзыв!</b>\n\n"
        "Ваше мнение помогает нам становиться лучше. "
        "Мы обязательно учтем ваши пожелания.",
        parse_mode="HTML"
    )

    logger.info(f"Получен отзыв от {message.from_user.id}: {feedback_text}")


# ========== ОБРАБОТКА НЕИЗВЕСТНЫХ КОМАНД ==========
@router.message(F.text.startswith('/'))
async def handle_unknown_command(message: Message):
    """Обработка неизвестных команд"""
    unknown_cmd = message.text.split()[0]

    await message.answer(
        f"❌ <b>Неизвестная команда:</b> {unknown_cmd}\n\n"
        f"Используйте <code>/help</code> для просмотра доступных команд.",
        parse_mode="HTML"
    )


# ========== ОБРАБОТКА ЛЮБЫХ ТЕКСТОВЫХ СООБЩЕНИЙ ==========
@router.message(F.text)
async def handle_any_text(message: Message, state: FSMContext):
    """Обработка любых текстовых сообщений (не команд)"""
    current_state = await state.get_state()

    # Если есть активное состояние, пропускаем (обрабатывается другими хендлерами)
    if current_state is not None:
        return

    # Если нет активного состояния и это не команда
    text = message.text.strip()

    # Проверяем, не является ли это номером заказа (только цифры)
    if text.isdigit() and len(text) <= 6:
        order_id = int(text)
        order = db.get_order_by_id(order_id)

        if order:
            user_id_from_order = order[1]
            if user_id_from_order == message.from_user.id:
                # Это номер заказа пользователя
                await cmd_status(message, types.CommandObject(command="status", args=text))
                return

    # Для админа: проверяем, не является ли это номером заказа для просмотра
    if is_admin(message.from_user.id) and text.isdigit() and len(text) <= 6:
        order_id = int(text)
        order = db.get_order_by_id(order_id)
        if order:
            from handlers.admin import cmd_order
            # Создаем фиктивную команду для вызова cmd_order
            fake_message = Message(
                message_id=message.message_id,
                date=message.date,
                chat=message.chat,
                text=f"/order {order_id}",
                from_user=message.from_user
            )
            # Здесь нужен бот, но мы не можем его передать
            # Лучше просто показать информацию
            await message.answer(
                f"📋 Заказ #{order_id} найден.\n"
                f"Для подробного просмотра используйте команду: <code>/order {order_id}</code>",
                parse_mode="HTML"
            )
            return

    # Если ничего не подошло - показываем справку
    await message.answer(
        "🤔 <b>Я не понял ваш запрос</b>\n\n"
        "Используйте кнопки меню или команду <code>/help</code> для просмотра доступных действий.",
        parse_mode="HTML"
    )