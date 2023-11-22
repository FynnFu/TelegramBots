import inspect
import logging
import os
import threading

import telebot
from django.db import transaction
from django.shortcuts import redirect, render
from dotenv import load_dotenv
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from ANTIBOT.models import TelegramUsers, Channels

load_dotenv()

TOKEN = os.getenv("TOKEN_ANTIBOT")

Bot = telebot.TeleBot(TOKEN)

CHANNEL_ID = -1002033981480


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
        return redirect('ANTIBOT:console')

    @staticmethod
    def stop(request):
        if Console.botThread is not None:
            if Console.botThread.is_alive():
                Bot.stop_polling()
        print(f'Bot is now stopping in a separate thread.')
        return redirect('ANTIBOT:console')

    @staticmethod
    def render(request):
        name = Bot.get_my_name().name
        context = {
            'bot_name': name
        }
        return render(request, 'antibot/console.html', context)


@Bot.chat_join_request_handler()
def approve_request(message):
    msg = f"Привет! Я ANTIBOT система.\n" \
          f"\n" \
          f"Для одобрения заявки, пройди капчу:"
    keyboard = InlineKeyboardMarkup()
    button = InlineKeyboardButton(text="Я человек 👤", callback_data='success')
    keyboard.add(button)
    try:
        Bot.send_message(message.from_user.id, msg, reply_markup=keyboard)
    except ApiTelegramException as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name)


@Bot.callback_query_handler(func=lambda call: call.data == 'success')
@transaction.atomic
def success(call):
    try:
        if not TelegramUsers.objects.filter(id=call.from_user.id).exists():
            user = TelegramUsers(
                id=call.from_user.id,
                username=call.from_user.username,
                first_name=call.from_user.first_name,
                last_name=call.from_user.last_name,
                blocked=False,
                is_staff=False
            )
            user.save()

        try:
            Bot.approve_chat_join_request(CHANNEL_ID, call.from_user.id)
            Bot.edit_message_text(chat_id=call.from_user.id,
                                  message_id=call.message.message_id,
                                  text="✅ Капча пройдена, вы добавлены в канал",
                                  reply_markup=None)
        except ApiTelegramException as ex:
            if "USER_ALREADY_PARTICIPANT" in str(ex):
                Bot.edit_message_text(chat_id=call.from_user.id,
                                      message_id=call.message.message_id,
                                      text="✅ Вы уже в канале",
                                      reply_markup=None)
            if "HIDE_REQUESTER_MISSING" in str(ex):
                Bot.edit_message_text(chat_id=call.from_user.id,
                                      message_id=call.message.message_id,
                                      text="❌ Приглашение не найдено, подайте заявку еще раз",
                                      reply_markup=None)
    except ApiTelegramException as ex:
        send_error_for_admins(call, ex, inspect.currentframe().f_code.co_name)


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
