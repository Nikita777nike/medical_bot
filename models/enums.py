# models/enums.py
from enum import Enum


class OrderStatus(str, Enum):
    """Статусы заказов"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PAID = "paid"
    CANCELLED = "cancelled"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    NEEDS_NEW_DOCS = "needs_new_docs"
    CREATED = "created"
    DOCS_UPLOADED = "docs_uploaded"


class DocumentType(str, Enum):
    """Типы документов"""
    PHOTO = "photo"
    PDF = "pdf"
    DOC = "doc"
    DOCX = "docx"
    TEXT = "text"
    OTHER = "other"


class PaymentStatus(str, Enum):
    """Статусы платежей"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class DiscountType(str, Enum):
    """Типы скидок"""
    PERCENT = "percent"
    FIXED = "fixed"
    REFERRAL = "referral"
    PROMO = "promo"


class ServiceType(str, Enum):
    """Типы услуг (дополнительно, если нужно строгое типирование)"""
    BLOOD_ANALYSIS = "Анализы крови/мочи"
    BIOCHEMISTRY = "Биохимия крови"
    HORMONES = "Гормоны"
    GENERAL_BLOOD = "Общий анализ крови"
    GENERAL_URINE = "Общий анализ мочи"
    LIPIDOGRAM = "Липидограмма"
    LIVER_TESTS = "Печеночные пробы"
    COAGULOGRAM = "Коагулограмма"
    ULTRASOUND = "УЗИ"
    XRAY = "Рентген"
    MRI = "МРТ"
    CT = "КТ"
    ECG = "ЭКГ"
    HOLTER = "Холтер"
    FLUOROGRAPHY = "Флюорография"
    DOCTOR_REPORT = "Врачебное заключение"
    HOSPITAL_EXTRACT = "Выписка из стационара"
    TREATMENT_PLAN = "Назначения лечения"
    SURGERY_PROTOCOL = "Протокол операции"
    CONSULTATION_RESULT = "Результаты консультации"


class UserRole(str, Enum):
    """Роли пользователей"""
    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"


class ClarificationType(str, Enum):
    """Типы уточнений"""
    TEXT = "text"
    PHOTO = "photo"
    DOCUMENT = "document"
    ADMIN_REQUEST = "admin_request"


class TaxStatus(str, Enum):
    """Статусы налоговой отчетности"""
    NOT_REPORTED = "not_reported"
    REPORTED = "reported"
    PENDING_REPORT = "pending_report"


# Константы для удобства использования
DEFAULT_PRICE = 490
MAX_DOCUMENTS = 10
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
CLARIFICATION_TIME_LIMIT_HOURS = 24
REFERRER_BONUS_PERCENT = 10
REFERRED_DISCOUNT_PERCENT = 5
AGREEMENT_VERSION = "2.1"