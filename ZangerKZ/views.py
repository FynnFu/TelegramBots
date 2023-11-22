import inspect
import logging
import os
import threading

import openai
import telebot
from django.db import transaction
from django.shortcuts import redirect, render
from dotenv import load_dotenv
from openai import RateLimitError, OpenAI
from telebot import types

from TelegramBots import settings
from ZangerKZ.models import *

load_dotenv()

TOKEN = os.getenv("TOKEN_ZANGERKZ")

Bot = telebot.TeleBot(TOKEN)

client = OpenAI(api_key=settings.API_KEY)


class Console:
    botThread = None

    @staticmethod
    def bot_polling():
        Bot.polling(none_stop=True, interval=0)

    @staticmethod
    def run(request):
        if Console.botThread is not None:
            if not Console.botThread.is_alive():
                Console.botThread = threading.Thread(target=Console.bot_polling)
                Console.botThread.start()
        else:
            Console.botThread = threading.Thread(target=Console.bot_polling)
            Console.botThread.start()
        print(f'Bot is now running in a separate thread.')
        return redirect('ZangerKZ:console')

    @staticmethod
    def stop(request):
        if Console.botThread is not None:
            if Console.botThread.is_alive():
                Bot.stop_polling()
        print(f'Bot is now stopping in a separate thread.')
        return redirect('ZangerKZ:console')

    @staticmethod
    def render(request):
        name = Bot.get_my_name().name
        context = {
            'bot_name': name
        }
        return render(request, 'zangerkz/console.html', context)


@Bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton(text='Я согласен(-на) ✅', callback_data='agree')
    markup.add(btn1)
    Bot.send_message(message.from_user.id, "Данный бот находится на этапе разработки!\n"
                                           "Для улучшения качества сервиса происходит сбор данных, "
                                           "для продолжения нужно Ваше согласие", reply_markup=markup)


@Bot.callback_query_handler(func=lambda call: call.data == 'agree')
@transaction.atomic
def agree(call):
    if not TelegramUsers.objects.filter(id=call.from_user.id).exists():
        user = TelegramUsers(
            id=call.from_user.id,
            username=call.from_user.username,
            first_name=call.from_user.first_name,
            last_name=call.from_user.last_name,
            blocked=False,
            is_staff=False,
            messages='[]'
        )
        user.save()

    Bot.send_message(call.from_user.id,
                     "Привет! 🤖 Я - ZangerKZ, твой юридический помощник от KazNU! 🌐 \n"
                     "\n"
                     "Можешь задавать любые юридические вопросы. 💡\n"
                     "\n"
                     "Жду твои вопросы! 🗣",
                     reply_markup=menu(call))


def menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("➕ Начать новый диалог"),
    )
    markup.add(
        types.KeyboardButton("👤 Мой профиль")
    )
    return markup


@Bot.message_handler(commands=['start_new_dialog'])
@Bot.callback_query_handler(func=lambda call: call.data == 'start_new_dialog')
@Bot.message_handler(func=lambda message: message.text == '➕ Начать новый диалог')
def start_new_dialog(message):
    try:
        user_id = message.from_user.id
        user = TelegramUsers.objects.get(id=user_id)
        user.clear_messages()
        content = "🤖 Привет! Я ZangerKZ. Чем я могу тебе помочь?"
        user.add_message("assistant", content)
        Bot.send_message(message.from_user.id, text=content, reply_markup=menu(message))

    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name)


@Bot.callback_query_handler(func=lambda call: call.data == 'profile')
@Bot.message_handler(func=lambda message: message.text == '👤 Мой профиль')
def profile(message):
    user = TelegramUsers.objects.get(id=message.from_user.id)

    text = f"👤: {user.first_name} {user.last_name} ({user.username})\n"

    if type(message) == types.Message:
        Bot.send_message(user.id, text=text, reply_markup=menu(message))
    elif type(message) == types.CallbackQuery:
        Bot.edit_message_text(
            chat_id=message.message.chat.id,
            message_id=message.message.message_id,
            text=text,
        )


@Bot.callback_query_handler(func=lambda call: call.data == 'positive')
@Bot.callback_query_handler(func=lambda call: call.data == 'negative')
@transaction.atomic
def save_review(call):
    user = TelegramUsers.objects.get(id=call.message.reply_to_message.from_user.id)

    review = Reviews(
        author=user,
        question=call.message.reply_to_message.text,
        answer=call.message.text,
        review=call.data)
    review.save()

    Bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=None)
    Bot.send_message(call.message.reply_to_message.from_user.id, "Спасибо за ваш отзыв", reply_markup=menu(call.message))


def generate_gpt_response(prompt, message):
    try:
        prompt_update = 'Заголовок: тут заголовок\n' \
                        'Ответ: тут ответ на вопрос\n' \
                        'Дата: тут дата информации\n' \
                        'Источник: тут ссылка на источник' \
                        f'Вопрос: {prompt}'

        completion = client.chat.completions.create(
            model="gpt-4-0314",
            messages=[
                {
                    "role": "user",
                    "content": f"{prompt_update}",
                },
            ],
        )

        return completion.choices[0].message.content
    except RateLimitError as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name)
        return "❗️ Системная ошибка ❗️"
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name)
        return "❗️ Системная ошибка ❗️"


def load_text_from_files(file_paths):
    text = ""

    for file_path in file_paths:
        with open(file_path, "r", encoding="utf-8") as file:
            text += file.read() + "\n"

    return text


def send_error_for_admins(message, ex, method_name):
    user_id = None
    if message is not None:
        Bot.send_message(message.from_user.id,
                         "⚠️ Произошла непредвиденная ошибка, сообщение об ошибке уже отправлено модерации.\n"
                         "Подождите пару минут и повторите попытку.")
        user_id = message.from_user.id
    admins = TelegramUsers.objects.filter(is_staff=True)
    text = "❗️ Сообщение от системы ❗️\n" \
           f"User ID: {user_id}\n" \
           f"Method: {method_name}\n" \
           f"Error type: {type(ex).__name__}\n" \
           f"Error message: {str(ex)}\n"
    logging.error(text)
    for admin in admins:
        Bot.send_message(admin.id, text)
    print(text)


@Bot.message_handler(func=lambda message: True)
def handle_messages(message):
    try:
        user_id = message.from_user.id
        user = TelegramUsers.objects.get(id=user_id)

        if message.text == "➕ Начать новый диалог" or message.text == "/start_new_dialog" \
                or message.text == "👤 Мой профиль":
            return
        else:
            thinking_message = Bot.send_message(message.from_user.id,
                                                "🧠 Думаю над ответом...",
                                                reply_to_message_id=message.message_id)
            user.add_message("user", message.text)

            gpt_response = generate_gpt_response(user.get_messages(), message)

            markup = types.InlineKeyboardMarkup()
            positively = types.InlineKeyboardButton(text='Хороший ответ✅', callback_data='positive')
            negative = types.InlineKeyboardButton(text='Плохой ответ❌', callback_data='negative')
            markup.add(positively)
            markup.add(negative)

            Bot.edit_message_text(chat_id=message.from_user.id,
                                  message_id=thinking_message.message_id,
                                  text=gpt_response,
                                  reply_markup=markup)

            user.add_message("assistant", gpt_response)
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name)
