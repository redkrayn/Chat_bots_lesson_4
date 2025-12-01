from environs import Env

env = Env()
env.read_env()


class Config:
    redis_host = env('REDIS_HOST', 'localhost')
    redis_port = env.int('REDIS_PORT', 6379)
    redis_password = env('REDIS_PASSWORD', None)
    redis_db = env.int('REDIS_DB', 0)

    path_quiz_question = env('PATH_QUIZ_QUESTIONS')

    telegram_bot_token = env('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = env.int('TELEGRAM_CHAT_ID')
    vk_token = env('VK_TOKEN')


config = Config()
