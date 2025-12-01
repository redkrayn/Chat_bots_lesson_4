import random
from functools import partial

import vk_api
import telegram

from config import config
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.longpoll import VkLongPoll, VkEventType
from utils import parse_quiz_questions, setup_logging, launch_redis


class UserState:
    NEW_QUESTION = 'new_question'
    ANSWERING = 'answering'


def send_message(vk, user_id, message, keyboard=None):
    params = {
        'user_id': user_id,
        'message': message,
        'random_id': random.randint(1, 1000000)
    }
    if keyboard:
        params['keyboard'] = keyboard.get_keyboard()
    vk.messages.send(**params)


def create_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('Новый вопрос', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('Сдаться', color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button('Мой счёт', color=VkKeyboardColor.SECONDARY)
    return keyboard


def handle_start(vk, user_id, redis_db, keyboard):
    user_info = vk.users.get(user_ids=[user_id])
    user_name = user_info[0]['first_name']

    message = f'Здравствуйте, {user_name}!'
    send_message(vk, user_id, message, keyboard)

    redis_db.set(f'user:{user_id}:state', UserState.NEW_QUESTION)
    return UserState.NEW_QUESTION


def handle_new_question(vk, user_id, redis_db, keyboard, quiz):
    question = random.choice(list(quiz.keys()))
    answer = quiz[question]

    redis_db.set(f'user:{user_id}:question', question)
    redis_db.set(f'user:{user_id}:answer', answer)
    redis_db.set(f'user:{user_id}:state', UserState.ANSWERING)

    send_message(vk, user_id, question, keyboard)
    return UserState.ANSWERING


def handle_solution_attempt(vk, user_id, user_message, redis_db, keyboard):
    stored_answer = redis_db.get(f'user:{user_id}:answer')
    stored_answer = stored_answer.decode('utf-8')

    if user_message.lower().strip() == stored_answer.lower().strip():
        redis_db.incr(f'user:{user_id}:score')
        send_message(vk, user_id, 'Правильно! Поздравляю! Для следующего вопроса нажми «Новый вопрос»', keyboard)

        redis_db.delete(f'user:{user_id}:question')
        redis_db.delete(f'user:{user_id}:answer')
        redis_db.set(f'user:{user_id}:state', UserState.NEW_QUESTION)
        return UserState.NEW_QUESTION
    else:
        send_message(vk, user_id, 'Неправильно… Попробуешь ещё раз?', keyboard)
        return UserState.ANSWERING


def handle_surrender(vk, user_id, redis_db, keyboard, quiz):
    answer = redis_db.get(f'user:{user_id}:answer')
    if not answer:
        send_message(vk, user_id, 'Нет активного вопроса', keyboard)
        redis_db.set(f'user:{user_id}:state', UserState.NEW_QUESTION)
        return UserState.NEW_QUESTION

    answer = answer.decode('utf-8')
    send_message(vk, user_id, f'Правильный ответ: {answer}', keyboard)

    redis_db.delete(f'user:{user_id}:question')
    redis_db.delete(f'user:{user_id}:answer')

    return handle_new_question(vk, user_id, redis_db, keyboard, quiz)


def handle_score(vk, user_id, redis_db, keyboard):
    user_score = redis_db.get(f'user:{user_id}:score')
    if user_score is None:
        user_score = 0
    else:
        user_score = int(user_score.decode('utf-8'))

    send_message(vk, user_id, f'Твой текущий счёт: {user_score} очков', keyboard)

    current_state = redis_db.get(f'user:{user_id}:state')
    if current_state:
        return current_state.decode('utf-8')
    else:
        redis_db.set(f'user:{user_id}:state', UserState.NEW_QUESTION)
        return UserState.NEW_QUESTION


def main():
    vk_token = config.vk_token
    telegram_chat_id = config.telegram_chat_id
    telegram_bot_token = config.telegram_bot_token

    tg_bot = telegram.Bot(token=telegram_bot_token)

    vk_session = vk_api.VkApi(token=vk_token)
    vk = vk_session.get_api()
    longpoll = VkLongPoll(vk_session)

    redis_db = launch_redis()
    quiz = parse_quiz_questions()

    logger_name = 'vk_quiz_bot'
    logger = setup_logging(logger_name, tg_bot, telegram_chat_id)

    keyboard = create_keyboard()

    try:
        logger.info('VK бот запущен')

        command_handlers = {
            'Начать': handle_start,
            '/start': handle_start,
            'Новый вопрос': partial(handle_new_question, quiz=quiz),
            'Сдаться': partial(handle_surrender, quiz=quiz),
            'Мой счёт': handle_score,
        }

        for event in longpoll.listen():
            if not (event.type == VkEventType.MESSAGE_NEW and event.to_me):
                continue

            user_id = event.user_id
            user_message = event.text

            state_key = f'user:{user_id}:state'
            current_state = redis_db.get(state_key)
            current_state = current_state.decode('utf-8') if current_state else UserState.NEW_QUESTION
            if not current_state:
                redis_db.set(state_key, UserState.NEW_QUESTION)

            handler = command_handlers.get(user_message)
            if handler:
                handler(vk, user_id, redis_db, keyboard)
                continue

            if current_state == UserState.ANSWERING:
                handle_solution_attempt(vk, user_id, user_message, redis_db, keyboard)
                continue

            send_message(vk, user_id, 'Нажмите «Новый вопрос» чтобы начать викторину', keyboard)

    except Exception as e:
        logger.error(f'Бот упал с ошибкой: {e}', exc_info=True)


if __name__ == '__main__':
    main()
