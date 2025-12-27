# handlers/states.py
from aiogram.fsm.state import State, StatesGroup

class OrderState(StatesGroup):
    """Состояния для процесса заказа"""
    waiting_for_service = State()
    waiting_for_promo = State()
    waiting_for_payment = State()
    waiting_for_demographics = State()
    waiting_for_docs_and_questions = State()
    waiting_for_clarification = State()
    waiting_for_contact = State()


class AdminState(StatesGroup):
    """Состояния для админ-панели"""
    waiting_for_template = State()
    waiting_for_promo_creation = State()
    waiting_for_price_change = State()