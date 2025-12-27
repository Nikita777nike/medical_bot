# handlers/admin.py
import asyncio
import json
import csv
import tempfile
import os
from datetime import datetime, timedelta
from io import StringIO, BytesIO
from html import escape as html_escape
import logging

from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
    FSInputFile
)
from aiogram.fsm.context import FSMContext
from handlers.states import AdminState
from database import db
from utils.keyboards import (
    create_admin_menu,
    create_admin_order_actions_keyboard,
    create_admin_template_keyboard
)
from models.enums import OrderStatus, DiscountType

logger = logging.getLogger(__name__)

router = Router()


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def format_date(date_str: str) -> str:
    """Форматирование даты для отображения"""
    try:
        if isinstance(date_str, str):
            dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            return dt.strftime('%d.%m.%Y %H:%M')
        elif isinstance(date_str, datetime):
            return date_str.strftime('%d.%m.%Y %H:%M')
    except:
        pass
    return str(date_str)[:16] if date_str else "н/д"


def get_status_emoji(status: str) -> str:
    """Получить эмодзи для статуса"""
    status_emojis = {
        'pending': '⏳',
        'processing': '🔄',
        'completed': '✅',
        'paid': '💰',
        'cancelled': '❌',
        'awaiting_clarification': '❓',
        'needs_new_docs': '📎'
    }
    return status_emojis.get(status, '📝')


# ========== ПРОВЕРКА ДОСТУПА ==========

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    # Временно возвращаем True для отладки
    # В production нужно импортировать config и проверять config.ADMIN_ID
    return True


# ========== СТАТИСТИКА ==========

@router.message(F.text == "📊 Статистика")
async def handle_statistics(message: Message):
    """Показать статистику"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        stats = db.get_statistics()

        # Формируем сообщение со статистикой
        stats_text = f"""<b>📊 СТАТИСТИКА СЕРВИСА</b>

<b>📈 ОБЩАЯ СТАТИСТИКА:</b>
• Всего заказов: {stats['total_orders']}
• Сегодня: {stats['today_orders']}
• Уникальных пользователей: {stats['unique_users']}
• Приняли соглашение: {stats['agreements_accepted']}

<b>📋 СТАТУСЫ ЗАКАЗОВ:</b>
• Ожидают ответа: {stats['pending_orders']}
• В обработке: {stats['completed_orders']}
• Уточняются: {stats['clarification_orders']}
• Нужны документы: {stats['new_docs_orders']}
• Оплачено: {stats['paid_orders']}

<b>💰 ФИНАНСЫ:</b>
• Общая выручка: {stats['total_revenue']}₽
• Средний чек: {stats['avg_price']}₽
• Сумма скидок: {stats['total_discounts']}₽
• Промокоды: {stats['promo_discounts']:.2f}₽
• Неотчитано в налоговой: {stats.get('unreported_amount', 0)}₽ ({stats.get('unreported_payments', 0)} платежей)

<b>⭐ ОЦЕНКИ:</b>
• Всего оценок: {stats['total_ratings']}
• Средняя оценка: {stats['avg_rating']:.1f}/5"""

        # Распределение оценок
        if stats['rating_distribution']:
            stats_text += "\n<b>📊 РАСПРЕДЕЛЕНИЕ ОЦЕНОК:</b>"
            for rating, count in stats['rating_distribution']:
                stars = "⭐" * rating
                stats_text += f"\n{stars}: {count}"

        # Статистика по уточнениям
        stats_text += f"""
<b>❓ УТОЧНЕНИЯ:</b>
• Всего уточняющих вопросов: {stats['total_clarifications']}

<b>🎫 ПРОМОКОДЫ:</b>
• Всего промокодов: {stats['total_promo_codes']}
• Использований: {stats['promo_uses']}
• Скидка по промокодам: {stats['promo_discounts']:.2f}₽

<b>📋 ПО ТИПАМ УСЛУГ:</b>"""

        # Статистика по типам услуг
        if stats['service_stats']:
            for service_type, count, avg_price, total_revenue in stats['service_stats']:
                if avg_price:
                    stats_text += f"\n• {service_type}: {count} зак., {avg_price:.0f}₽ средн., {total_revenue or 0}₽ всего"
                else:
                    stats_text += f"\n• {service_type}: {count} зак."

        # Статистика по дням
        if stats['daily_stats']:
            stats_text += "\n\n<b>📅 ЗАКАЗЫ ПО ДНЯМ (7 дней):</b>"
            for date_str, count, revenue in stats['daily_stats']:
                stats_text += f"\n• {date_str}: {count} зак., {revenue or 0}₽"

        # Реферальная статистика
        try:
            referral_stats = db.get_all_referrals_stats()
            stats_text += f"""

<b>👥 РЕФЕРАЛЬНАЯ СИСТЕМА:</b>
• Всего рефералов: {referral_stats['total_referrals']}
• Завершенных заказов: {referral_stats['completed_referrals']}
• Выплачено бонусов: {referral_stats['total_bonuses']:.2f}₽
• Предоставлено скидок: {referral_stats['total_discounts']:.2f}₽"""
        except Exception as e:
            logger.error(f"Ошибка получения реферальной статистики: {e}")

        # Команды для админа
        stats_text += """

<b>🔧 КОМАНДЫ:</b>
<code>/export_stats</code> - экспорт в CSV
<code>/mark_tax_reported [order_id]</code> - отметить как отчитанный
<code>/backup_db</code> - создать резервную копию БД
<code>/cleanup_old</code> - очистить старые данные"""

        await message.answer(stats_text, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка получения статистики: {str(e)[:200]}", reply_markup=create_admin_menu())
        logger.error(f"Ошибка получения статистики: {e}")


# ========== ВСЕ ЗАКАЗЫ ==========

@router.message(F.text == "📋 Все заказы")
async def handle_all_orders(message: Message):
    """Показать все заказы (последние сверху)"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        orders = db.get_all_orders(limit=20)

        if not orders:
            await message.answer("📭 Нет заказов", reply_markup=create_admin_menu())
            return

        text_lines = []
        text_lines.append(f"<b>📋 ПОСЛЕДНИЕ ЗАКАЗЫ ({len(orders)})</b>\n")
        text_lines.append("<i>Новые заказы вверху ↓</i>\n")

        for order in orders:
            order_id = order[0]
            user_id = order[1]
            username = order[2]
            service_type = order[8] if len(order) > 8 else "Не указано"
            status = order[9] if len(order) > 9 else "pending"
            created_at = order[10] if len(order) > 10 else None
            price = order[14] if len(order) > 14 else 0
            original_price = order[15] if len(order) > 15 else price

            status_emoji = get_status_emoji(status)
            datetime_str = format_date(created_at)

            short_service = service_type[:25] + "..." if len(service_type) > 25 else service_type
            short_username = username[:15] if username else "без username"
            discount = original_price - price if original_price and price else 0

            text_lines.append(f"<b>{status_emoji} #{order_id} • {datetime_str}</b>")
            text_lines.append(f"👤 @{short_username} (ID: {user_id})")
            text_lines.append(f"📋 {short_service}")
            text_lines.append(f"💰 {price}₽ (скидка: {discount}₽)")
            text_lines.append(f"📊 Статус: <b>{status}</b>")
            text_lines.append(f"🔧 /order_{order_id}")
            text_lines.append("─" * 40)
            text_lines.append("")

        text = "\n".join(text_lines)
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка отображения всех заказов: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


# ========== ОЖИДАЮЩИЕ ЗАКАЗЫ ==========

@router.message(F.text == "⏳ Ожидающие")
async def handle_pending_orders(message: Message):
    """Показать ожидающие заказы"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        orders = db.get_pending_orders(limit=20)

        if not orders:
            await message.answer("✅ Нет ожидающих заказов", reply_markup=create_admin_menu())
            return

        text_lines = []
        text_lines.append(f"<b>⏳ ОЖИДАЮЩИЕ ОБРАБОТКИ ({len(orders)})</b>\n")

        for order in orders:
            order_id = order[0]
            user_id = order[1]
            username = order[2]
            service_type = order[8] if len(order) > 8 else "Не указано"
            status = order[9] if len(order) > 9 else "pending"
            created_at = order[10] if len(order) > 10 else None
            price = order[14] if len(order) > 14 else 0
            age = order[3] if len(order) > 3 else None
            sex = order[4] if len(order) > 4 else None
            questions = order[5] if len(order) > 5 else None

            status_emoji = get_status_emoji(status)
            datetime_str = format_date(created_at)

            # Демография
            demographics = []
            if age:
                demographics.append(f"{age} лет")
            if sex and sex != "Не указан":
                demographics.append(sex)
            demo_text = ", ".join(demographics) if demographics else "не указано"

            short_question = questions[:50] + "..." if questions and len(questions) > 50 else (
                        questions or "нет вопроса")
            short_service = service_type[:30] + "..." if len(service_type) > 30 else service_type
            short_username = username[:15] if username else "без username"

            text_lines.append(f"<b>{status_emoji} #{order_id} • {datetime_str} • {status}</b>")
            text_lines.append(f"👤 @{short_username} (ID: {user_id})")
            text_lines.append(f"📋 {short_service}")
            text_lines.append(f"💰 {price}₽")
            text_lines.append(f"👤 {demo_text}")
            text_lines.append(f"❓ {short_question}")
            text_lines.append(f"🔧 /order_{order_id}")
            text_lines.append("─" * 40)
            text_lines.append("")

        text = "\n".join(text_lines)
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка отображения ожидающих заказов: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


# ========== БЭКАП БАЗЫ ДАННЫХ ==========

@router.message(F.text == "💾 Бэкап")
async def handle_backup(message: Message):
    """Создать резервную копию БД"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        await message.answer("🔄 Создание резервной копии БД...", reply_markup=create_admin_menu())

        success = db.backup()

        if success:
            await message.answer("✅ Резервная копия БД успешно создана!", reply_markup=create_admin_menu())
        else:
            await message.answer("❌ Не удалось создать резервную копию БД.", reply_markup=create_admin_menu())

    except Exception as e:
        logger.error(f"Ошибка создания бэкапа: {e}")
        await message.answer(f"❌ Ошибка при создании бэкапа: {str(e)[:200]}", reply_markup=create_admin_menu())


# ========== ПРОМОКОДЫ ==========

@router.message(F.text == "🎫 Промокоды")
async def handle_promo_codes(message: Message):
    """Управление промокодами"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        promo_codes = db.get_all_promo_codes()

        if not promo_codes:
            text = """<b>🎫 УПРАВЛЕНИЕ ПРОМОКОДАМИ</b>

Промокоды не созданы.

<b>🔧 Команды:</b>
<code>/create_promo [код] [тип] [значение] [использований]</code>
Пример: <code>/create_promo SUMMER percent 15 100</code>
<code>/deactivate_promo [код]</code> - деактивировать промокод"""
            await message.answer(text, parse_mode="HTML", reply_markup=create_admin_menu())
            return

        text_lines = ["<b>🎫 АКТИВНЫЕ ПРОМОКОДЫ</b>\n"]

        for promo in promo_codes:
            promo_id, code, discount_type, discount_value, uses_left, valid_until, created_at, is_active, description = promo

            status = "✅ Активен" if is_active else "❌ Неактивен"
            uses_text = f"{uses_left} использований" if uses_left != -1 else "безлимит"
            valid_text = f"до {format_date(valid_until)}" if valid_until else "бессрочный"

            text_lines.append(f"<b>🔸 {code}</b> - {status}")
            text_lines.append(f"Скидка: {discount_value}{'%' if discount_type == 'percent' else '₽'}")
            text_lines.append(f"Использований: {uses_text}")
            text_lines.append(f"Действует: {valid_text}")
            if description:
                text_lines.append(f"Описание: {description}")
            text_lines.append(f"Создан: {format_date(created_at)}")
            text_lines.append(f"🔧 <code>/deactivate_promo_{code}</code>")
            text_lines.append("─" * 30)
            text_lines.append("")

        text_lines.append("\n<b>🔧 Команды:</b>")
        text_lines.append("<code>/create_promo [код] [тип] [значение] [использований]</code>")
        text_lines.append("Пример: <code>/create_promo SUMMER percent 15 100</code>")

        text = "\n".join(text_lines)
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка отображения промокодов: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


@router.message(Command("create_promo"))
async def cmd_create_promo(message: Message):
    """Создание нового промокода"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        args = message.text.split()[1:]
        if len(args) < 3:
            await message.answer(
                "❌ <b>Некорректный формат команды</b>\n\n"
                "Использование: <code>/create_promo [код] [тип] [значение] [использований] [срок]</code>\n"
                "Примеры:\n"
                "<code>/create_promo SUMMER percent 15 100</code> - 15% скидка, 100 использований\n"
                "<code>/create_promo WELCOME fixed 100 1</code> - 100₽ скидка, 1 использование\n"
                "<code>/create_promo TEST percent 10 -1 2024-12-31</code> - до 31.12.2024",
                parse_mode="HTML"
            )
            return

        code = args[0].upper()
        discount_type = args[1].lower()  # 'percent' или 'fixed'
        discount_value = float(args[2])
        uses_left = int(args[3]) if len(args) > 3 else -1
        valid_until = None

        if len(args) > 4:
            try:
                valid_until = datetime.strptime(args[4], '%Y-%m-%d')
            except ValueError:
                await message.answer("❌ Неверный формат даты. Используйте YYYY-MM-DD")
                return

        success = db.create_promo_code(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            uses_left=uses_left,
            valid_until=valid_until,
            description=f"Создан администратором {message.from_user.id}"
        )

        if success:
            await message.answer(f"✅ Промокод <b>{code}</b> успешно создан!", parse_mode="HTML")
        else:
            await message.answer(f"❌ Не удалось создать промокод. Возможно, такой код уже существует.")

    except Exception as e:
        logger.error(f"Ошибка создания промокода: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")


# ========== РЕФЕРАЛЫ ==========

@router.message(F.text == "👥 Рефералы")
async def handle_referrals(message: Message):
    """Статистика по рефералам"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        stats = db.get_all_referrals_stats()

        text = f"""<b>👥 РЕФЕРАЛЬНАЯ СИСТЕМА</b>

<b>📊 ОБЩАЯ СТАТИСТИКА:</b>
• Всего реферальных связей: {stats['total_referrals']}
• Завершенных заказов: {stats['completed_referrals']}
• Выплачено бонусов: {stats['total_bonuses']:.2f}₽
• Предоставлено скидок: {stats['total_discounts']:.2f}₽

<b>🏆 ТОП-10 РЕФЕРЕРОВ:</b>"""

        if stats['top_referrers']:
            for i, (referrer_id, count, total_bonus) in enumerate(stats['top_referrers'], 1):
                text += f"\n{i}. ID {referrer_id}: {count} чел., {total_bonus or 0:.2f}₽"
        else:
            text += "\nПока нет активных рефереров."

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка отображения реферальной статистики: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


# ========== ШАБЛОНЫ ==========

@router.message(F.text == "📝 Шаблоны")
async def handle_templates(message: Message):
    """Управление шаблонами ответов"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        templates = db.get_quick_templates()

        if not templates:
            text = """<b>📝 БЫСТРЫЕ ШАБЛОНЫ ОТВЕТОВ</b>

Шаблоны не созданы.

<b>🔧 Команды:</b>
<code>/add_template [название] [текст]</code> - добавить шаблон
Пример: <code>/add_template Приветствие "Добрый день! Спасибо за обращение."</code>"""
            await message.answer(text, parse_mode="HTML", reply_markup=create_admin_menu())
            return

        text_lines = ["<b>📝 ДОСТУПНЫЕ ШАБЛОНЫ</b>\n"]

        for template in templates:
            template_id, name, text, created_at, updated_at = template
            text_lines.append(f"<b>🔸 #{template_id}: {name}</b>")
            text_lines.append(f"Текст: {text[:100]}{'...' if len(text) > 100 else ''}")
            text_lines.append(f"Обновлен: {format_date(updated_at)}")
            text_lines.append(f"🔧 <code>/use_template_{template_id} [order_id]</code>")
            text_lines.append("─" * 30)
            text_lines.append("")

        text_lines.append("\n<b>🔧 Команды:</b>")
        text_lines.append("<code>/add_template [название] [текст]</code> - добавить шаблон")
        text_lines.append("<code>/edit_template [id] [новый текст]</code> - редактировать шаблон")
        text_lines.append("<code>/delete_template [id]</code> - удалить шаблон")

        text = "\n".join(text_lines)
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка отображения шаблонов: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


@router.message(Command("add_template"))
async def cmd_add_template(message: Message):
    """Добавление нового шаблона"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        text = message.text
        if not text.startswith('/add_template '):
            return

        # Извлекаем название и текст шаблона
        parts = text.split(' ', 2)
        if len(parts) < 3:
            await message.answer(
                "❌ <b>Некорректный формат</b>\n\n"
                "Использование: <code>/add_template [название] [текст]</code>\n"
                "Пример: <code>/add_template Приветствие \"Добрый день! Спасибо за обращение.\"</code>",
                parse_mode="HTML"
            )
            return

        name = parts[1]
        template_text = parts[2]

        success = db.add_quick_template(name=name, text=template_text)

        if success:
            await message.answer(f"✅ Шаблон <b>{name}</b> успешно добавлен!", parse_mode="HTML")
        else:
            await message.answer("❌ Не удалось добавить шаблон.")

    except Exception as e:
        logger.error(f"Ошибка добавления шаблона: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")


# ========== КОМАНДА АДМИН ==========

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Команда админ-меню"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    await message.answer("👨‍💻 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=create_admin_menu())


# ========== РАБОТА С КОНКРЕТНЫМ ЗАКАЗОМ ==========

@router.message(Command("order"))
async def cmd_order(message: Message, bot: Bot):
    """Просмотр и управление конкретным заказом"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("❌ Укажите номер заказа: <code>/order [id]</code>", parse_mode="HTML")
            return

        order_id = int(args[1])
        order = db.get_order_by_id(order_id)

        if not order:
            await message.answer(f"❌ Заказ #{order_id} не найден")
            return

        # Распаковываем данные заказа
        order_id = order[0]
        user_id = order[1]
        username = order[2]
        age = order[3]
        sex = order[4]
        questions = order[5]
        documents = order[6] if len(order) > 6 else None
        document_types = order[7] if len(order) > 7 else None
        service_type = order[8] if len(order) > 8 else "Не указано"
        status = order[9] if len(order) > 9 else "pending"
        created_at = order[10] if len(order) > 10 else None
        updated_at = order[11] if len(order) > 11 else None
        answered_at = order[12] if len(order) > 12 else None
        admin_id = order[13] if len(order) > 13 else None
        price = order[14] if len(order) > 14 else 0
        original_price = order[15] if len(order) > 15 else price
        payment_status = order[16] if len(order) > 16 else "pending"
        discount_applied = order[25] if len(order) > 25 else 0
        promo_code = order[27] if len(order) > 27 else None
        rating = order[22] if len(order) > 22 else None

        status_emoji = get_status_emoji(status)
        datetime_str = format_date(created_at)

        # Демография
        demographics = []
        if age:
            demographics.append(f"{age} лет")
        if sex and sex != "Не указан":
            demographics.append(sex)
        demo_text = ", ".join(demographics) if demographics else "не указано"

        # Документы
        docs_count = 0
        if documents:
            try:
                docs_list = json.loads(documents)
                docs_count = len(docs_list)
            except:
                docs_count = 0

        text = f"""<b>{status_emoji} ЗАКАЗ #{order_id}</b>

<b>👤 КЛИЕНТ:</b>
• ID: {user_id}
• Username: @{username or 'не указан'}

<b>📋 ИНФОРМАЦИЯ О ЗАКАЗЕ:</b>
• Услуга: {service_type}
• Стоимость: {price}₽ (скидка: {discount_applied}₽)
• Промокод: {promo_code or 'нет'}
• Статус оплаты: {payment_status}
• Статус заказа: {status}

<b>👤 ДЕМОГРАФИЯ:</b>
• {demo_text}

<b>❓ ВОПРОС КЛИЕНТА:</b>
{questions or 'нет вопроса'}

<b>📎 ДОКУМЕНТЫ:</b>
• Загружено: {docs_count} файлов

<b>📅 ВРЕМЕННЫЕ МЕТКИ:</b>
• Создан: {datetime_str}
• Обновлен: {format_date(updated_at)}
• Ответ дан: {format_date(answered_at)}

<b>⭐ ОЦЕНКА:</b>
{'⭐' * rating if rating else 'еще нет оценки'}

<b>🔧 ДОСТУПНЫЕ ДЕЙСТВИЯ:</b>"""

        keyboard = create_admin_order_actions_keyboard(order_id)
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка просмотра заказа: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}", reply_markup=create_admin_menu())


# ========== ОТВЕТ НА ЗАКАЗ ==========

@router.message(Command("send"))
async def cmd_send_reply(message: Message, bot: Bot):
    """Отправка ответа клиенту"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        args = message.text.split(' ', 2)
        if len(args) < 3:
            await message.answer("❌ Укажите номер заказа и текст: <code>/send [id] [текст]</code>", parse_mode="HTML")
            return

        order_id = int(args[1])
        reply_text = args[2]

        order = db.get_order_by_id(order_id)
        if not order:
            await message.answer(f"❌ Заказ #{order_id} не найден")
            return

        user_id = order[1]

        # Отправляем ответ пользователю
        try:
            await bot.send_message(
                user_id,
                f"<b>👨‍⚕️ Ответ по вашему заказу #{order_id}</b>\n\n"
                f"{reply_text}\n\n"
                f"<i>Если у вас остались вопросы, задайте их в течение 24 часов.</i>",
                parse_mode="HTML"
            )

            # Обновляем статус заказа
            db.update_order_status(order_id, OrderStatus.COMPLETED, message.from_user.id)

            # Добавляем запись о ответе
            db.add_clarification(
                order_id=order_id,
                user_id=message.from_user.id,
                message_text=reply_text,
                is_from_user=False
            )

            await message.answer(f"✅ Ответ отправлен пользователю (заказ #{order_id})")

        except Exception as e:
            await message.answer(f"❌ Не удалось отправить сообщение пользователю: {str(e)[:200]}")

    except Exception as e:
        logger.error(f"Ошибка отправки ответа: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")


# ========== ГЛАВНОЕ МЕНЮ ==========

@router.message(F.text == "🏠 Главное меню")
async def handle_main_menu(message: Message, state: FSMContext):
    """Возврат в главное меню пользователя"""
    await state.clear()

    # Для админа показываем админ-меню
    if is_admin(message.from_user.id):
        await message.answer(
            "🏠 <b>Главное меню администратора</b>",
            parse_mode="HTML",
            reply_markup=create_admin_menu()
        )
    else:
        # Если обычный пользователь нажал эту кнопку в админ-меню
        from handlers.user import create_main_menu
        await message.answer(
            "🏠 <b>Главное меню</b>",
            parse_mode="HTML",
            reply_markup=create_main_menu()
        )


# ========== ЭКСПОРТ СТАТИСТИКИ ==========

@router.message(Command("export_stats"))
async def cmd_export_stats(message: Message):
    """Экспорт статистики в CSV"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        stats = db.get_statistics()

        # Создаем CSV файл в памяти
        output = StringIO()
        writer = csv.writer(output)

        # Заголовки
        writer.writerow(['Метрика', 'Значение'])

        # Данные
        writer.writerow(['Всего заказов', stats['total_orders']])
        writer.writerow(['Заказов сегодня', stats['today_orders']])
        writer.writerow(['Уникальных пользователей', stats['unique_users']])
        writer.writerow(['Приняли соглашение', stats['agreements_accepted']])
        writer.writerow(['Ожидают ответа', stats['pending_orders']])
        writer.writerow(['В обработке', stats['completed_orders']])
        writer.writerow(['Уточняются', stats['clarification_orders']])
        writer.writerow(['Нужны документы', stats['new_docs_orders']])
        writer.writerow(['Оплачено', stats['paid_orders']])
        writer.writerow(['Общая выручка', stats['total_revenue']])
        writer.writerow(['Средний чек', stats['avg_price']])
        writer.writerow(['Сумма скидок', stats['total_discounts']])
        writer.writerow(['Всего оценок', stats['total_ratings']])
        writer.writerow(['Средняя оценка', stats['avg_rating']])

        # Конвертируем в байты
        csv_bytes = output.getvalue().encode('utf-8')

        # Отправляем файл
        await message.answer_document(
            document=BufferedInputFile(csv_bytes,
                                       filename=f"statistics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"),
            caption="📊 Статистика сервиса"
        )

    except Exception as e:
        logger.error(f"Ошибка экспорта статистики: {e}")
        await message.answer(f"❌ Ошибка экспорта: {str(e)[:200]}")


# ========== ПОМЕТКА НАЛОГОВОГО ОТЧЕТА ==========

@router.message(Command("mark_tax_reported"))
async def cmd_mark_tax_reported(message: Message):
    """Пометить платеж как отчитанный в налоговой"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ запрещен")
        return

    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("❌ Укажите номер заказа: <code>/mark_tax_reported [id]</code>", parse_mode="HTML")
            return

        order_id = int(args[1])

        success = db.mark_tax_reported(order_id)

        if success:
            await message.answer(f"✅ Платеж по заказу #{order_id} отмечен как отчитанный в налоговой")
        else:
            await message.answer(f"❌ Не удалось отметить платеж. Проверьте номер заказа.")

    except Exception as e:
        logger.error(f"Ошибка отметки налогового отчета: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")