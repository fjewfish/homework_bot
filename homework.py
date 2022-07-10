import os
import sys
import time
import logging
import requests
import telegram.ext
from json import JSONDecodeError
from logging import StreamHandler
from dotenv import load_dotenv
from http import HTTPStatus
from exceptions import ApiAnswerError, TelegramSendMessageError, StatusError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = StreamHandler(stream=sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info(f'Бот отправил сообщение "{message}"')
    except telegram.error.TelegramError as err:
        raise TelegramSendMessageError(f'Ошибка при отправке сообщения {err}')


def get_api_answer(current_timestamp: int) -> dict:
    """Делает запрос к эндпоинту API-сервиса."""
    logger.info('Начался запрос к API')
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params,
        )
        if response.status_code != HTTPStatus.OK:
            raise ApiAnswerError(
                f'Эндпоинт {ENDPOINT} недоступен. '
                f'Код ответа API: {response.status_code} '
                f'headers: {HEADERS}'
            )
        homework_statuses = response.json()
        logger.info('Запрос к API успешно завершен')
    except requests.exceptions.RequestException as err:
        raise ApiAnswerError(f'Эндпоинт {ENDPOINT} недоступен. Ошибка: {err}')
    except (JSONDecodeError, ValueError) as err:
        raise ValueError(f'Ошибка при декодирование json. Ошибка: {err}')
    return homework_statuses


def check_response(response: dict) -> list:
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        raise TypeError(f'Нверный тип данных ответа: {type(response)} != dict')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(f'Нверный тип данных ДЗ: {type(response)} != list')
    current_date = response.get('current_date')
    if homeworks and (not homeworks or not current_date):
        raise KeyError('Отсутствуют ключи от API')
    logger.info('Ответ от API прошел проверку')
    return homeworks


def parse_status(homework: list) -> str:
    """Извлекает из домашней работе статус этой работы."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if not homework_name or not homework_status:
        raise KeyError('Отсутствуют ключи от последней работы')
    verdict = HOMEWORK_STATUSES.get(homework_status)
    if not verdict:
        raise StatusError(
            f'Недокументированный статус домашней работы {homework_status}'
        )
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def error_tokens_message() -> str:
    """Возвращает сообщение для ошибки остутствия переменных окружения."""
    message = 'Отсутствуют обязательные переменные окружения: '
    for token_name, token in {'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
                              'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
                              'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID}.items():
        if not token:
            message += f'{token_name}, '
    return message + 'программа принудительно остановлена!'


def error_tokens_try_send_message(message: str) -> None:
    """Пытается отправить соодщение при отсутвие переменных окружения."""
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            send_message(telegram.Bot(token=TELEGRAM_TOKEN), message)
        except TelegramSendMessageError as err:
            logger.error(f'Сбой в работе программы: {err}')


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        message = error_tokens_message()
        logger.critical(message)
        error_tokens_try_send_message(message)
        sys.exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    prev_message = None
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if homeworks:
                status = parse_status(homeworks[0])
                if status != prev_message:
                    send_message(bot, status)
                    prev_message = status
            else:
                logger.debug('В ответе API отсутствуют новые статусы')
            current_timestamp = int(time.time())
        except Exception as err:
            message = f'Сбой в работе программы: {err}'
            logger.error(message)
            if message != prev_message:
                send_message(bot, message)
                prev_message = message
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
