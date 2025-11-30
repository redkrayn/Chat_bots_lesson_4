import random

from environs import Env
from utils import get_quiz, setup_logging, launch_redis
from enum import Enum, auto
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler
from telegram import ReplyKeyboardMarkup


class State(Enum):
    NEW_QUESTION = auto()
    ANSWERING = auto()


def start(update, context):
    user = update.message.from_user

    keyboard = [
        ['Новый вопрос', 'Сдаться'],
        ['Мой счёт']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    update.message.reply_text(
        f'Здравствуйте, {user.first_name}!',
        reply_markup=reply_markup
    )

    return State.NEW_QUESTION


def handle_any_message(update, context):
    user = update.message.from_user

    keyboard = [
        ['/start']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    update.message.reply_text(
        f'Привет, {user.first_name}!\n'
        'Я бот для викторин. Чтобы начать игру, просто нажми команду /start',
        reply_markup=reply_markup
    )


def handle_text_in_new_question_state(update, context):
    keyboard = [
        ['Новый вопрос', 'Сдаться'],
        ['Мой счёт']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    update.message.reply_text(
        'Чтобы получить новый вопрос, нажмите кнопку «Новый вопрос»',
        reply_markup=reply_markup
    )

    return State.NEW_QUESTION


def handle_new_question_request(update, context):
    user_id = update.message.from_user.id
    quiz = get_quiz()

    question = random.choice(list(quiz.keys()))
    answer = quiz[question]

    context.bot_data['redis_db'].set(f'user:{user_id}:question', question)
    context.bot_data['redis_db'].set(f'user:{user_id}:answer', answer)

    update.message.reply_text(question)

    return State.ANSWERING


def handle_solution_attempt(update, context):
    user_id = update.message.from_user.id
    user_message = update.message.text
    redis_db = context.bot_data['redis_db']

    stored_answer = redis_db.get(f'user:{user_id}:answer')
    stored_answer = stored_answer.decode('utf-8')

    if user_message.lower().strip() == stored_answer.lower().strip():
        redis_db.incr(f'user:{user_id}:score')
        update.message.reply_text('Правильно! Поздравляю! Для следующего вопроса нажми «Новый вопрос»')

        redis_db.delete(f'user:{user_id}:question')
        redis_db.delete(f'user:{user_id}:answer')

        return State.NEW_QUESTION
    else:
        update.message.reply_text('Неправильно… Попробуешь ещё раз?')
        return State.ANSWERING


def handle_surrender(update, context):
    user_id = update.message.from_user.id
    redis_db = context.bot_data['redis_db']

    answer = redis_db.get(f'user:{user_id}:answer')
    if not answer:
        update.message.reply_text('Нет активного вопроса')

        return State.NEW_QUESTION

    answer = answer.decode('utf-8')

    update.message.reply_text(f'Правильный ответ: {answer}')

    redis_db.delete(f'user:{user_id}:question')
    redis_db.delete(f'user:{user_id}:answer')

    return handle_new_question_request(update, context)


def handle_score(update, context):
    user_id = update.message.from_user.id
    redis_db = context.bot_data['redis_db']

    user_score = redis_db.get(f'user:{user_id}:score')
    if user_score is None:
        user_score = 0
    else:
        user_score = int(user_score.decode('utf-8'))

    update.message.reply_text(f'Твой текущий счёт: {user_score} очков')

    if redis_db.exists(f'user:{user_id}:answer'):
        return State.ANSWERING
    else:
        return State.NEW_QUESTION


def main():
    env = Env()
    env.read_env()

    telegram_bot_token = env('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = env('TELEGRAM_CHAT_ID')

    updater = Updater(telegram_bot_token)
    dp = updater.dispatcher

    dp.bot_data['redis_db'] = launch_redis()

    logger_name = 'tg_echo_bot'
    logger = setup_logging(logger_name, updater.bot, telegram_chat_id)

    try:
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                State.NEW_QUESTION: [
                    MessageHandler(Filters.regex('^Новый вопрос$'), handle_new_question_request),
                    MessageHandler(Filters.regex('^Мой счёт$'), handle_score),
                    MessageHandler(Filters.text & ~Filters.command, handle_text_in_new_question_state)
                ],
                State.ANSWERING: [
                    MessageHandler(Filters.regex('^Сдаться$'), handle_surrender),
                    MessageHandler(Filters.regex('^Мой счёт$'), handle_score),
                    MessageHandler(Filters.text & ~Filters.command, handle_solution_attempt)
                ],
            },
            fallbacks=[]
        )

        dp.add_handler(conv_handler)
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_any_message))

        logger.info('Бот запущен')

        updater.start_polling()
        updater.idle()

    except Exception as e:
        logger.error(f'Бот упал с ошибкой: {e}', exc_info=True)


if __name__ == '__main__':
    main()
