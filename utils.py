import os
import re
import redis
import logging

from environs import Env


class TelegramLogsHandler(logging.Handler):
    def __init__(self, tg_bot, chat_id):
        super().__init__()
        self.chat_id = chat_id
        self.tg_bot = tg_bot

    def emit(self, record):
        log_entry = self.format(record)
        self.tg_bot.send_message(chat_id=self.chat_id, text=log_entry)


def setup_logging(logger_name, tg_bot=None, chat_id=None):
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(message)s'
    )

    tg_handler = TelegramLogsHandler(tg_bot, chat_id)
    tg_handler.setLevel(logging.INFO)
    tg_handler.setFormatter(formatter)
    logger.addHandler(tg_handler)

    return logger


def get_quiz():
    folder_path = 'quiz-questions'
    all_files = os.listdir(folder_path)
    questions_dict = {}
    lenghtsss = 0

    for filename in all_files:
        file_path = os.path.join(folder_path, filename)
        with open(file_path, 'r', encoding='KOI8-R') as file:
            file_contents = file.read()

        sections = file_contents.split('\n\n')
        current_question = None

        for section in sections:
            if re.match(r'^Вопрос\s+\d+:', section):
                current_question = section
                questions_dict[current_question] = ""

            elif section.startswith('Ответ:'):
                symbols_to_remove = '[]{}()"".!?;:'
                clean_answer = section.replace('Ответ:', '').strip()
                for symbol in symbols_to_remove:
                    clean_answer = clean_answer.replace(symbol, '')
                questions_dict[current_question] = clean_answer

        lenghtsss += 1
        if lenghtsss == 1:
            break

    return questions_dict


def launch_redis():
    env = Env()
    env.read_env()

    redis_host = env('REDIS_HOST', 'localhost')
    redis_port = env.int('REDIS_PORT', 6379)
    redis_password = env('REDIS_PASSWORD', None)
    redis_db = env.int('REDIS_DB', 0)

    redis_client = redis.Redis(
        host=redis_host,
        port=redis_port,
        password=redis_password,
        db=redis_db,
        decode_responses=False
    )

    return redis_client
