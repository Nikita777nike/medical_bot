# handlers/user.py
import asyncio
import uuid
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ContentType
)

from utils.config import config
from database import db
from utils.keyboards import (
    create_main_menu,
    create_service_keyboard,
    create_promo_keyboard,
    create_demographics_keyboard,
    create_docs_questions_keyboard,
    get_service_prices
)
from utils.agreement import AgreementHandler
from utils.validators import DocumentValidator
from models.enums import OrderStatus, DocumentType, DiscountType
from handlers.payment import send_invoice_to_user
# Уберите определение OrderState из этого файла и импортируйте из states.py
from handlers.states import OrderState

import logging

logger = logging.getLogger(__name__)

router = Router()





# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def html_escape(text: str) -> str:
    """Экранирование HTML-символов"""
    if not text:
        return ""
    return (text.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def get_progress_bar(step: int, total_steps: int = 5) -> str:
    """Создает визуальный прогресс-бар"""
    filled = '█' * step
    empty = '░' * (total_steps - step)
    return f"[{filled}{empty}] {step}/{total_steps}"


def bold(text: str) -> str:
    """Жирный текст"""
    return f"<b>{html_escape(text)}</b>"


# В handlers/user.py добавьте обработчики:
@router.callback_query(F.data == "agreement_accept")
async def handle_agreement_accept(callback: types.CallbackQuery, state: FSMContext):
    """Обработка принятия соглашения"""
    user_id = callback.from_user.id

    # Записываем факт принятия в БД
    success = db.record_agreement_acceptance(
        user_id=user_id,
        agreement_version=AgreementHandler.AGREEMENT_VERSION,
        ip_info=""  # Можно получить IP, если нужно
    )

    if success:
        await callback.message.edit_text(
            "✅ <b>Соглашение принято!</b>\n\n"
            "Теперь вы можете создавать заказы.",
            parse_mode="HTML"
        )
        await callback.answer("Соглашение принято")

        # Переходим к созданию заказа
        await start_order_new_flow(callback.message, state)
    else:
        await callback.answer("❌ Ошибка при сохранении соглашения")


@router.callback_query(F.data == "agreement_full")
async def handle_agreement_full(callback: types.CallbackQuery):
    """Показать полное соглашение"""
    full_text = agreement_handler.get_full_agreement()
    keyboard = agreement_handler.create_full_agreement_keyboard()

    await callback.message.edit_text(full_text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "agreement_back")
async def handle_agreement_back(callback: types.CallbackQuery):
    """Вернуться к краткому соглашению"""
    short_text = agreement_handler.get_short_agreement()
    keyboard = agreement_handler.create_agreement_keyboard()

    await callback.message.edit_text(short_text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "agreement_reject")
async def handle_agreement_reject(callback: types.CallbackQuery):
    """Обработка отказа от соглашения"""
    await callback.message.edit_text(
        "❌ <b>Вы отказались от пользовательского соглашения.</b>\n\n"
        "Для использования сервиса необходимо принять соглашение.\n"
        "Если у вас есть вопросы, свяжитесь с поддержкой.",
        parse_mode="HTML"
    )
    await callback.answer("Соглашение отклонено")

# ========== КЛАССЫ ДЛЯ КЛАВИАТУР ==========
class RatingHandler:
    """Класс для работы с оценками"""

    @staticmethod
    def create_rating_keyboard(order_id: int) -> InlineKeyboardMarkup:
        """Создать клавиатуру с оценкой 1-5 звёзд"""
        buttons = []
        row = []
        for i in range(1, 6):
            row.append(InlineKeyboardButton(
                text="⭐" * i,
                callback_data=f"rate_{order_id}_{i}"
            ))
            if i == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        return InlineKeyboardMarkup(inline_keyboard=buttons)


class ClarificationHandler:
    """Класс для работы с уточнениями"""

    @staticmethod
    def create_clarification_keyboard(order_id: int) -> InlineKeyboardMarkup:
        """Создать клавиатуру для действий после ответа"""
        buttons = [
            [
                InlineKeyboardButton(text="❓ Задать вопрос",
                                     callback_data=f"clarify_{order_id}"),
                InlineKeyboardButton(text="⭐ Оценить",
                                     callback_data=f"rate_menu_{order_id}")
            ],
            [
                InlineKeyboardButton(text="👨‍💻 Связаться",
                                     callback_data=f"support_{order_id}")
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def create_simple_rating_keyboard(order_id: int) -> InlineKeyboardMarkup:
        """Простая клавиатура только с оценкой"""
        buttons = [
            [InlineKeyboardButton(text="⭐ Оценить заказ",
                                  callback_data=f"rate_menu_{order_id}")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)


# ========== КОМАНДА START ==========
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Начало работы с ботом"""
    await state.clear()

    # Проверяем реферальную ссылку
    args = message.text.split()
    referrer_id = None

    if len(args) > 1 and args[1].startswith('ref_'):
        try:
            referrer_id = int(args[1].replace('ref_', ''))
            if referrer_id != message.from_user.id:
                db.create_referral(referrer_id, message.from_user.id)
                logger.info(f"Реферальная ссылка использована: {referrer_id} → {message.from_user.id}")
        except (ValueError, IndexError):
            pass

    welcome_text = f"""👨‍⚕️ <b>Добро пожаловать в медицинский сервис расшифровки анализов RazMedBot</b>

🏥 <b>Профессиональная помощь в понимании ваших медицинских документов</b>

✨ <b>Наш подход к расшифровке:</b>

🤖 <b>Искусственный интеллект</b>
• Мгновенный анализ медицинских данных
• Сравнение с возрастными и половными нормами
• Выявление ключевых показателей

👨‍⚕️ <b>Проверка медицинским специалистом</b>
• Экспертная оценка результатов
• Учет индивидуальных особенностей
• Рекомендации по дальнейшим действиям

<b>Выберите действие из меню ниже ⤵️</b>"""

    if message.from_user.id == config.ADMIN_ID:
        # Импорт внутри функции, чтобы избежать циклической зависимости
        from handlers.admin import create_admin_menu
        await message.answer(welcome_text, parse_mode="HTML", reply_markup=create_admin_menu())
    else:
        await message.answer(welcome_text, parse_mode="HTML", reply_markup=create_main_menu())

    logger.info(f"Пользователь {message.from_user.username} начал работу")


# ========== КОМАНДА HELP ==========
@router.message(Command("help"))
async def cmd_help(message: Message):
    """Показать справку по командам"""
    help_text = """<b>🆘 СПРАВКА ПО КОМАНДАМ</b>

<b>Основные команды:</b>
/start - Начать работу с ботом
/help - Показать эту справку
/cancel - Отменить текущее действие

<b>Действия:</b>
• 🩺 Создать заказ - Оформить новый заказ
• 📋 Мои заказы - Посмотреть историю заказов
• 👨‍⚕️ О сервисе - Информация о сервисе
• 👨‍💻 Связаться - Связаться с поддержкой
• 👥 Пригласить друга - Реферальная программа

<b>Для администраторов:</b>
• 📊 Статистика - Статистика сервиса
• 📋 Все заказы - Все заказы системы
• ⏳ Ожидающие - Ожидающие обработки заказы
• 🎫 Промокоды - Управление промокодами
• 👥 Рефералы - Статистика по рефералам
• 📝 Шаблоны - Быстрые шаблоны ответов"""

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

    await asyncio.sleep(0.5)

    # Возвращаем в главное меню
    if message.from_user.id == config.ADMIN_ID:
        from handlers.admin import create_admin_menu
        await message.answer("Выберите действие:", reply_markup=create_admin_menu())
    else:
        await message.answer("Выберите действие:", reply_markup=create_main_menu())


# ========== СОЗДАНИЕ ЗАКАЗА ==========
@router.message(F.text == "🩺 Создать заказ")
async def start_order_new_flow(message: Message, state: FSMContext):
    """Начало создания заказа"""
    # Проверяем, принимал ли пользователь уже соглашение
    if not db.check_agreement_accepted(message.from_user.id):
        # Показываем краткое соглашение
        text = AgreementHandler.get_short_agreement()
        keyboard = AgreementHandler.create_agreement_keyboard()

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        return

    # Если соглашение принято - начинаем новый поток
    await state.clear()
    await state.set_state(OrderState.waiting_for_service)

    instruction_text = f"""<b>🩺 ШАГ 1 из 5: ВЫБОР УСЛУГИ</b>

{get_progress_bar(1)}

<b>Выберите тип медицинских документов для расшифровки:</b>

<code>──────────────────────────────</code>
<b>📋 АНАЛИЗЫ (нужен возраст/пол)</b>
<code>──────────────────────────────</code>
• Анализы крови и мочи
• Биохимия, гормоны
• Коагулограммы
<code>💎 190-290₽</code>

<code>──────────────────────────────</code>
<b>🏥 ИССЛЕДОВАНИЯ</b>
<code>──────────────────────────────</code>
• УЗИ, МРТ, КТ, рентген
• ЭКГ, Холтер
<code>💎 190-390₽</code>

<code>──────────────────────────────</code>
<b>📄 ДОКУМЕНТАЦИЯ</b>
<code>──────────────────────────────</code>
• Врачебные заключения
• Выписки, назначения
• Протоколы операций
<code>💎 190₽</code>

<b>Выберите услугу из списка ниже:</b>"""

    keyboard, _ = create_service_keyboard()
    await message.answer(
        instruction_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ========== ОТМЕНА ЗАКАЗА ==========
@router.message(F.text == "❌ Отменить заказ")
async def cancel_order(message: Message, state: FSMContext):
    """Отмена заказа пользователем"""
    await state.clear()
    await message.answer(
        "❌ Заказ отменен.",
        reply_markup=ReplyKeyboardRemove()
    )

    await asyncio.sleep(0.5)

    if message.from_user.id == config.ADMIN_ID:
        from handlers.admin import create_admin_menu
        await message.answer(
            "Выберите действие:",
            reply_markup=create_admin_menu()
        )
    else:
        await message.answer(
            "Выберите действие:",
            reply_markup=create_main_menu()
        )


# ========== ПРИГЛАСИТЬ ДРУГА ==========
@router.message(F.text == "👥 Пригласить друга")
async def show_referral_info(message: Message, bot: Bot):
    """Показать информацию о реферальной программе"""
    try:
        # Получаем статистику
        stats = db.get_referrer_stats(message.from_user.id)

        # Получаем username бота для ссылки
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            if not bot_username:
                referral_link = f"https://t.me/{bot_info.id}?start=ref_{message.from_user.id}"
            else:
                referral_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
        except Exception as e:
            logger.error(f"Ошибка получения username бота: {e}")
            referral_link = f"t.me/ваш_бот?start=ref_{message.from_user.id}"

        referral_text = f"""<b>👥 ПРИГЛАСИТЬ ДРУГА</b>

💎 <b>Приглашайте друзей и получайте бонусы!</b>

<b>Как это работает:</b>
1. Вы приглашаете друга по своей ссылке
2. Друг получает <b>скидку {config.REFERRED_DISCOUNT_PERCENT}%</b> на первый заказ
3. Когда друг оплатит заказ, вы получаете <b>{config.REFERRER_BONUS_PERCENT}%</b> от суммы его заказа

<b>Ваша реферальная ссылка:</b>
<code>{referral_link}</code>

<b>Ваша статистика:</b>
• Приглашено друзей: {stats.get('total_referred', 0)}
• Из них сделали заказы: {stats.get('completed_referred', 0)}
• Всего заработано: {stats.get('total_bonus', 0):.2f}₽

<b>Просто отправьте другу эту ссылку!</b>"""

        await message.answer(referral_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка в show_referral_info: {e}")
        # Простой текст на случай ошибки
        await message.answer(
            f"👥 <b>Пригласить друга</b>\n\n"
            f"Ваша реферальная ссылка:\n"
            f"<code>t.me/ваш_бот?start=ref_{message.from_user.id}</code>\n\n"
            f"Приглашайте друзей и получайте {config.REFERRER_BONUS_PERCENT}% от их заказов!\n"
            f"Друзья получают скидку {config.REFERRED_DISCOUNT_PERCENT}% на первый заказ.",
            parse_mode="HTML"
        )


# ========== ОБРАБОТКА ВЫБОРА УСЛУГИ ==========
@router.message(OrderState.waiting_for_service)
async def handle_service_selection(message: Message, state: FSMContext):
    """Обработка выбора услуги"""
    if message.text == "❌ Отменить заказ":
        await cancel_order(message, state)
        return

    services = get_service_prices()
    selected_service = None
    service_info = None

    # Ищем выбранную услугу (убираем цену из текста)
    input_text = message.text
    for service_name in services.keys():
        # Проверяем, начинается ли текст с названия услуги
        if input_text.startswith(service_name):
            selected_service = service_name
            service_info = services[service_name]
            break

    if not selected_service:
        # Если не нашли услугу, показываем меню снова
        await message.answer(
            "❌ <b>Пожалуйста, выберите услугу с помощью кнопок ниже</b>\n\n"
            "Нажимайте только на кнопки с названиями услуг и ценами.",
            parse_mode="HTML"
        )

        # Показываем инструкцию и клавиатуру
        keyboard, category_info = create_service_keyboard()

        instruction_text = f"""<b>🩺 ШАГ 1 из 5: ВЫБОР УСЛУГИ</b>

{get_progress_bar(1)}

<b>Выберите тип медицинских документов для расшифровки:</b>

{category_info}

<b>Выберите услугу из списка ниже:</b>"""

        await message.answer(instruction_text, parse_mode="HTML", reply_markup=keyboard)
        return

    original_price = service_info["price"]
    needs_demographics = service_info["needs_demographics"]

    # Проверяем реферальную скидку
    has_referral_discount, discount_percent = db.check_referral_discount(message.from_user.id)
    final_price = original_price

    if has_referral_discount:
        discount_amount = original_price * (discount_percent / 100)
        final_price = max(0, original_price - discount_amount)
        discount_text = f"\n🎁 <b>Реферальная скидка: {discount_percent}% ({int(discount_amount)}₽)</b>"
    else:
        discount_text = ""

    await state.update_data(
        service_type=selected_service,
        original_price=original_price,
        current_price=int(final_price),
        needs_demographics=needs_demographics,
        discount_applied=original_price - final_price if has_referral_discount else 0,
        discount_type="referral" if has_referral_discount else None
    )

    await state.set_state(OrderState.waiting_for_promo)

    instruction_text = f"""<b>💎 ШАГ 2 из 5: ПРОМОКОД</b>

{get_progress_bar(2)}

✅ <b>Услуга выбрана:</b> {selected_service}
💰 <b>Стоимость:</b> {original_price}₽
{discount_text}
💰 <b>Итоговая цена:</b> <code>{int(final_price)}₽</code>

──────────────────────────────
<b>Есть промокод?</b>

Если у вас есть промокод на скидку, введите его сейчас.
Или нажмите "⏭️ Пропустить" для продолжения.

<b>Введите промокод:</b>"""

    await message.answer(
        instruction_text,
        parse_mode="HTML",
        reply_markup=create_promo_keyboard()
    )


@router.message(OrderState.waiting_for_docs_and_questions, F.photo)
async def handle_document_photo(message: Message, state: FSMContext):
    """Обработка фото документов с валидацией"""
    # Валидация
    is_valid, error_msg = await document_validator.validate_photo(message)
    if not is_valid:
        await message.answer(f"⚠️ {error_msg}")
        return

    # Дальнейшая обработка...
# Продолжение обработчика промокодов и других состояний...
# [Здесь должен быть остальной код из оригинального файла]

# ========== О СЕРВИСЕ ==========
@router.message(F.text == "👨‍⚕️ О сервисе")
async def about_service(message: Message):
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


# ========== МОИ ЗАКАЗЫ ==========
@router.message(F.text == "📋 Мои заказы")
async def show_my_orders(message: Message):
    """Показать заказы пользователя"""
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
            order_id, _, _, _, _, _, _, _, service_type, status, created_at, _, _, _, price, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _, _ = order

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

        orders_text += "\n<b>💡 Для просмотра деталей конкретного заскажите его номер в поддержку.</b>"

        await message.answer(orders_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при показе заказов: {e}")
        await message.answer(
            "❌ <b>Ошибка при загрузке ваших заказов</b>\n\n"
            "Попробуйте позже или обратитесь в поддержку.",
            parse_mode="HTML"
        )


# ========== ГЛАВНОЕ МЕНЮ ==========
@router.message(F.text == "🏠 Главное меню")
async def main_menu(message: Message, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()

    if message.from_user.id == config.ADMIN_ID:
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