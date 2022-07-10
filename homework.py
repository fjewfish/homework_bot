import os
import sys
import time
import logging
import requests
import telegram.ext
from json import JSONDecodeError
from dotenv import load_dotenv
from http import HTTPStatus
from exceptions import ApiAnswerError, SendMessageError, StatusError

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


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.info(f'Бот отправил сообщение "{message}"')
    except Exception as err:
        raise SendMessageError('Ошибка при отправке сообщения') from err


def get_api_answer(current_timestamp: int) -> dict:
    """Делает запрос к эндпоинту API-сервиса."""
    try:
        timestamp = current_timestamp or int(time.time())
        params = {'from_date': timestamp}
        logging.info(f'Запрос к API. Эндпоинт: {ENDPOINT}. headers: {HEADERS}')
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
        logging.info('Запрос к API успешно завершен')
    except (JSONDecodeError, ValueError) as err:
        raise ValueError('Ошибка при декодирование json') from err
    except Exception as err:
        raise ApiAnswerError(f'Эндпоинт {ENDPOINT} недоступен.') from err
    return homework_statuses


def check_response(response: dict) -> list:
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        raise TypeError(f'Нверный тип данных ответа: {type(response)} != dict')
    if ('homeworks' or 'current_date') not in response:
        raise KeyError('Отсутствуют ключи от API')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError(f'Нверный тип данных ДЗ: {type(response)} != list')
    logging.info('Ответ от API прошел проверку')
    return homeworks


def parse_status(homework: dict) -> str:
    """Извлекает из домашней работе статус этой работы."""
    if not isinstance(homework, dict):
        raise TypeError(f'Нверный тип данных ДЗ: {type(homework)} != dict')
    if ('homework_name' or 'status') not in homework:
        raise KeyError('Отсутствуют ключи от последней работы')
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_STATUSES:
        raise StatusError(
            f'Недокументированный статус домашней работы {homework_status}'
        )
    verdict = HOMEWORK_STATUSES.get(homework_status)
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


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        message = error_tokens_message()
        logging.critical(message)
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
                logging.debug('В ответе API отсутствуют новые статусы')
            current_timestamp = int(time.time())
        except Exception as err:
            message = f'Сбой в работе программы: {err}'
            logging.error(message)
            if message != prev_message:
                send_message(bot, message)
                prev_message = message
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        stream=sys.stdout,
    )
    main()
