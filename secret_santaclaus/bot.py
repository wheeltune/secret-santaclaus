import enum
import os
import traceback

import telebot

from .congratulations import Congratulations
from .database import Database

__all__ = ['bot']


TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode='Markdown')
database = Database()
congratulations = Congratulations()

states = dict()
class State(enum.Enum):
    NONE = 0,
    APPROVE = 1
    INTERESTS = 2


def message_handler(*args, **kwargs):
    def decorator(func):
        def wrapper(message):
            try:
                func(message)
            except:
                bot.send_message(message.chat.id, 'Упс, что-то пошло не так(')
                traceback.print_exc()
        return bot.message_handler(*args, **kwargs)(wrapper)
    return decorator


def is_authorized(func):
    def wrapped_func(message):
        user = database.find_user(telegram_id=message.from_user.id)
        event = database.find_event(1)

        if event.has_participant(user):
            return func(message)

        bot.send_message(message.chat.id, 'Чтобы продолжить взаимодействие необходимо завершить авторизацию, пингани @wheeltune')

    return wrapped_func


def is_admin(func):
    def wrapped_func(message):
        user = database.find_user(telegram_id=message.from_user.id)
        if user.is_admin():
            return func(message)
    return wrapped_func


@message_handler(commands=['start'])
def start(message):
    user = database.find_user(telegram_id=message.from_user.id)
    if user is None:
        database.create_user(message.from_user)
        bot.send_message(message.chat.id, 'Привет, рад с тобой познакомиться')
        bot.send_message(message.chat.id, 'Когда все соберутся, я пришлю тебе имя "жертвы"')
    else:
        bot.send_message(message.chat.id, 'Рад видеть тебя снова)')


@message_handler(commands=['addressee'])
@is_authorized
def addressee(message):
    user = database.find_user(telegram_id=message.from_user.id)
    event = database.find_event(1)

    addressee_user = event.find_victim(user)
    if addressee_user is None:
        bot.send_message(message.chat.id, 'Похоже, что ещё не всё готово, нужно немного подождать. Я скажу, когда будет всё')
    else:
        bot.send_message(message.chat.id, 'Напомню, жребий пал на [click me](tg://user?id={})'.format(addressee_user.telegram_id))


@message_handler(commands=['cancel'])
@is_authorized
def cancel(message):
    states[message.from_user.id] = State.NONE


@message_handler(commands=['my_interests'])
@is_authorized
def my_interests(message):
    user = database.find_user(telegram_id=message.from_user.id)
    event = database.find_event(1)

    bot.send_message(message.chat.id, 'Твои пожелания:')
    interests = event.find_interests(user)
    if interests is None:
        bot.send_message(message.chat.id, 'Ты пока не отметил свои пожелания')
    else:
        bot.send_message(message.chat.id, interests)


@message_handler(commands=['santa_interests'])
@is_authorized
def santa_interests(message):
    user = database.find_user(telegram_id=message.from_user.id)
    event = database.find_event(1)
    addressee_user = event.find_victim(user)

    bot.send_message(message.chat.id, 'Пожелания для санты:')
    interests = event.find_interests(addressee_user)
    if interests is None:
        bot.send_message(message.chat.id, 'Пожеланий пока нет(')
    else:
        bot.send_message(message.chat.id, interests)


@message_handler(commands=['set_interests'])
@is_authorized
def set_interests(message):
    bot.send_message(message.chat.id, 'Напиши свои пожелания, а я сообщю о них санте (только текстом)')
    states[message.from_user.id] = State.INTERESTS


@message_handler(func=lambda message: states.get(message.from_user.id, State.NONE) == State.INTERESTS)
@is_authorized
def do_set_interests(message):
    if message.text is None:
        bot.send_message(message.chat.id, 'Можно отправить только текст(')
        return

    user = database.find_user(telegram_id=message.from_user.id)
    event = database.find_event(1)

    event.save_interests(user, message.text)
    bot.send_message(message.chat.id, 'Понял, принял, записал')
    states[message.from_user.id] = State.NONE

    # addressee_user = event.find_victim(user)
    # if addressee_user is not None:
    #     bot.send_message(addressee_user.telegram_id, 'Обновились пожелания для санты:')
    #     bot.send_message(addressee_user.telegram_id, event.find_interests(addressee_user))


@message_handler(commands=['participants'])
@is_admin
def participants(message):
    event = database.find_event(1)

    user_ids = event.get_participants()
    if len(user_ids) == 0:
        bot.send_message(message.chat.id, 'Никто не состоит в этом событии')
        return

    users = map(lambda _: database.find_user(user_id=_), user_ids)
    names = map(lambda _: '[{} {}](tg://user?id={})'.format(_.first_name, _.second_name, _.telegram_id), users)
    bot.send_message(message.chat.id, '\n'.join(names))


@message_handler(commands=['build_victims'])
@is_admin
def build_victims(message):
    event = database.find_event(1)

    if event.was_build():
        bot.send_message(message.chat.id, 'Событие уже построено')
        return

    edges = event.build()
    edges = map(lambda _: (database.find_user(_[0]), database.find_user(_[1])), edges)
    for from_user, to_user in edges:
        bot.send_message(from_user.telegram_id, 'Будешь сантой для [click me](tg://user?id={})'.format(to_user.telegram_id))


@message_handler(commands=['approve'])
@is_admin
def approve(message):
    bot.send_message(message.chat.id, 'Скинь контакт или перешли сообщение')
    states[message.from_user.id] = State.APPROVE


@message_handler(func=lambda message: states.get(message.from_user.id, State.NONE) == State.APPROVE)
@is_admin
def do_approve(message):
    telegram_id = None
    if message.contact is not None and message.contact.user_id is not None:
        telegram_id = message.contact.user_id
    elif message.forward_from is not None:
        telegram_id = message.forward_from.id
    else:
        bot.send_message(message.chat.id, 'Из сообщения не очень понятно кто имеется ввиду')

    if telegram_id is not None:
        user = database.find_user(telegram_id=telegram_id)
        if user is not None:

            event = database.find_event(1)
            event.add_participant(user)

            bot.send_message(message.chat.id, 'Done')
            bot.send_message(telegram_id, 'Теперь можем и поболтать)')
        else:
            bot.send_message(message.chat.id, 'Не могу найти такого(')

    states[message.from_user.id] = State.NONE


@message_handler(func=lambda message: True)
@is_authorized
def unknown(message):
    bot.send_message(message.chat.id, congratulations.get_random(), parse_mode='html')
