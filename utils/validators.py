# utils/validators.py
import re
from typing import Tuple, Optional, Dict
from aiogram.types import Message
from models.enums import DocumentType
import logging

logger = logging.getLogger(__name__)


class DocumentValidator:
    """Класс для валидации документов и файлов"""

    # Поддерживаемые MIME-типы
    ALLOWED_MIME_TYPES: Dict[str, str] = {
        'image/jpeg': DocumentType.PHOTO.value,
        'image/png': DocumentType.PHOTO.value,
        'image/jpg': DocumentType.PHOTO.value,
        'application/pdf': DocumentType.PDF.value,
        'application/msword': DocumentType.DOC.value,
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': DocumentType.DOCX.value,
        'text/plain': DocumentType.TEXT.value
    }

    # Максимальные размеры файлов (в байтах)
    MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB
    MAX_DOCUMENT_SIZE = 20 * 1024 * 1024  # 20 MB
    MAX_DOCUMENTS_PER_ORDER = 10

    @staticmethod
    async def validate_photo(message: Message, max_size: int = None) -> Tuple[bool, str]:
        """
        Валидация фотографии

        Args:
            message: Сообщение с фото
            max_size: Максимальный размер в байтах (по умолчанию MAX_PHOTO_SIZE)

        Returns:
            Tuple[bool, str]: (успех, сообщение об ошибке)
        """
        if max_size is None:
            max_size = DocumentValidator.MAX_PHOTO_SIZE

        try:
            if not message.photo:
                return False, "Сообщение не содержит фото"

            # Получаем фото самого высокого качества
            photo = message.photo[-1]

            # Проверяем размер
            file_size = photo.file_size or 0
            if file_size > max_size:
                size_mb = max_size / (1024 * 1024)
                return False, f"Размер фото превышает {size_mb} МБ"

            # Проверяем наличие подписи (опционально, но желательно для медицинских документов)
            if not message.caption:
                logger.info(f"Фото от пользователя {message.from_user.id} без подписи")
                # Можно добавить предупреждение, но не блокировать
                # return False, "Добавьте описание к фото (например, 'анализ крови')"

            return True, ""

        except Exception as e:
            logger.error(f"Ошибка валидации фото: {e}")
            return False, f"Ошибка обработки фото: {str(e)[:100]}"

    @staticmethod
    async def validate_document(message: Message, max_size: int = None) -> Tuple[bool, str]:
        """
        Валидация документа

        Args:
            message: Сообщение с документом
            max_size: Максимальный размер в байтах (по умолчанию MAX_DOCUMENT_SIZE)

        Returns:
            Tuple[bool, str]: (успех, сообщение об ошибке)
        """
        if max_size is None:
            max_size = DocumentValidator.MAX_DOCUMENT_SIZE

        try:
            if not message.document:
                return False, "Сообщение не содержит документ"

            document = message.document

            # Проверяем размер
            file_size = document.file_size or 0
            if file_size > max_size:
                size_mb = max_size / (1024 * 1024)
                return False, f"Размер документа превышает {size_mb} МБ"

            # Проверяем MIME-тип
            mime_type = document.mime_type or ''
            if mime_type not in DocumentValidator.ALLOWED_MIME_TYPES:
                allowed_types = ', '.join([t.split('/')[-1] for t in DocumentValidator.ALLOWED_MIME_TYPES.keys()])
                return False, f"Неподдерживаемый формат файла. Разрешены: {allowed_types}"

            # Проверяем расширение файла
            file_name = document.file_name or ""
            if not DocumentValidator._validate_file_extension(file_name, mime_type):
                return False, "Некорректное расширение файла"

            # Для медицинских документов желательна подпись
            if not message.caption and not DocumentValidator._is_likely_medical_document(file_name):
                logger.info(f"Документ '{file_name}' от пользователя {message.from_user.id} без описания")

            return True, ""

        except Exception as e:
            logger.error(f"Ошибка валидации документа: {e}")
            return False, f"Ошибка обработки документа: {str(e)[:100]}"

    @staticmethod
    def _validate_file_extension(file_name: str, mime_type: str) -> bool:
        """Проверка соответствия расширения файла его MIME-типу"""
        if not file_name:
            return True  # Не можем проверить, но разрешаем

        file_extension = file_name.lower().split('.')[-1] if '.' in file_name else ''

        # Соответствие расширений и MIME-типов
        extension_mapping = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'txt': 'text/plain'
        }

        if file_extension in extension_mapping:
            return extension_mapping[file_extension] == mime_type

        return True  # Если расширение неизвестно, доверяем MIME-типу

    @staticmethod
    def _is_likely_medical_document(file_name: str) -> bool:
        """Проверка, похож ли файл на медицинский документ по названию"""
        if not file_name:
            return False

        file_name_lower = file_name.lower()

        medical_keywords = [
            'анализ', 'analysis', 'результат', 'result', 'заключение', 'conclusion',
            'выписка', 'extract', 'исследование', 'research', 'диагноз', 'diagnosis',
            'узи', 'ультразвук', 'us', 'мрт', 'mri', 'кт', 'ct', 'рентген', 'xray',
            'кровь', 'blood', 'моча', 'urine', 'гормон', 'hormone', 'биохимия', 'biochemistry'
        ]

        for keyword in medical_keywords:
            if keyword in file_name_lower:
                return True

        return False

    @staticmethod
    def validate_text_length(text: str, min_length: int = 10, max_length: int = 2000) -> Tuple[bool, str]:
        """
        Валидация длины текста (для вопросов и описаний)

        Args:
            text: Текст для проверки
            min_length: Минимальная длина
            max_length: Максимальная длина

        Returns:
            Tuple[bool, str]: (успех, сообщение об ошибке)
        """
        if not text or not text.strip():
            return False, "Текст не может быть пустым"

        text = text.strip()

        if len(text) < min_length:
            return False, f"Текст слишком короткий. Минимум {min_length} символов."

        if len(text) > max_length:
            return False, f"Текст слишком длинный. Максимум {max_length} символов."

        # Проверка на осмысленность (базовая)
        words = text.split()
        if len(words) < 3:
            return False, "Пожалуйста, напишите более развернутый вопрос"

        return True, ""

    @staticmethod
    def validate_age(age_str: str) -> Tuple[bool, Optional[int], str]:
        """
        Валидация возраста

        Args:
            age_str: Строка с возрастом

        Returns:
            Tuple[bool, Optional[int], str]: (успех, возраст, сообщение об ошибке)
        """
        try:
            if not age_str or not age_str.strip():
                return False, None, "Возраст не указан"

            age = int(age_str.strip())

            if age < 0:
                return False, None, "Возраст не может быть отрицательным"

            if age > 120:
                return False, None, "Пожалуйста, укажите реальный возраст (до 120 лет)"

            if age < 14:
                # Для несовершеннолетних может потребоваться согласие родителей
                logger.warning(f"Пользователь указал возраст {age} лет")
                return True, age, ""

            return True, age, ""

        except ValueError:
            return False, None, "Пожалуйста, укажите возраст цифрами"
        except Exception as e:
            logger.error(f"Ошибка валидации возраста: {e}")
            return False, None, f"Ошибка обработки возраста: {str(e)[:100]}"

    @staticmethod
    def validate_phone(phone: str) -> Tuple[bool, str]:
        """
        Валидация номера телефона (если понадобится в будущем)

        Args:
            phone: Номер телефона

        Returns:
            Tuple[bool, str]: (успех, сообщение об ошибке)
        """
        if not phone:
            return False, "Номер телефона не указан"

        # Убираем все нецифровые символы
        digits = re.sub(r'\D', '', phone)

        # Проверяем длину (для российских номеров)
        if len(digits) not in [10, 11]:
            return False, "Некорректная длина номера телефона"

        # Проверяем код страны/оператора
        if digits.startswith('7') or digits.startswith('8'):
            return True, ""

        return False, "Некорректный код страны/оператора"

    @staticmethod
    def validate_email(email: str) -> Tuple[bool, str]:
        """
        Валидация email (если понадобится в будущем)

        Args:
            email: Email адрес

        Returns:
            Tuple[bool, str]: (успех, сообщение об ошибке)
        """
        if not email:
            return False, "Email не указан"

        # Простая проверка регулярным выражением
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

        if re.match(pattern, email):
            return True, ""

        return False, "Некорректный формат email"

    @staticmethod
    def validate_promo_code(code: str) -> Tuple[bool, str]:
        """
        Валидация формата промокода

        Args:
            code: Промокод

        Returns:
            Tuple[bool, str]: (успех, сообщение об ошибке)
        """
        if not code or not code.strip():
            return False, "Промокод не указан"

        code = code.strip().upper()

        # Проверяем длину
        if len(code) < 3 or len(code) > 20:
            return False, "Промокод должен содержать от 3 до 20 символов"

        # Проверяем допустимые символы (буквы, цифры, дефисы, подчеркивания)
        if not re.match(r'^[A-Z0-9_-]+$', code):
            return False, "Промокод может содержать только буквы, цифры, дефисы и подчеркивания"

        # Проверяем, чтобы не был чисто числовым
        if code.isdigit():
            return False, "Промокод не может состоять только из цифр"

        return True, ""


# Создаем глобальный экземпляр для удобства использования
document_validator = DocumentValidator()