import inspect
import logging
import os
import subprocess
import threading
import time
import traceback
import telebot
import pymysql
from pymysql.cursors import DictCursor
from django.contrib.sites.models import Site
from django.db import transaction, connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv
from openai import RateLimitError, OpenAI
from telebot import types
from TelegramBots import settings
from ZangerKZ.models import *

load_dotenv()

logger = logging.getLogger('django')

try:
    if Tokens.objects.exists():
        TOKEN = Tokens.objects.first().telegram_bot_token
        API_KEY = Tokens.objects.first().openai_api_key
    else:
        TOKEN = "6524376393:AAGQEw6zkFNZ1Mz86XyPRrG18IbmhdmbO4w"
        API_KEY = ""

    URL = Site.objects.get_current().domain

except Exception as e:
    TOKEN = "6524376393:AAGQEw6zkFNZ1Mz86XyPRrG18IbmhdmbO4w"
    API_KEY = ""
    URL = "https://example.com/"
    logger.error(e)

WEBHOOK_URL = URL + "zangerkz/webhook/"

Bot = telebot.TeleBot(TOKEN)

client = OpenAI(api_key=API_KEY)


def requires_staff(func):
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.is_staff:
                return func(request, *args, **kwargs)

        return redirect(f'{reverse("admin:login")}?next={request.path}')

    return wrapper


def requires_db(func):
    @Bot.callback_query_handler(func=lambda call: call.data == 'check_subscribe')
    @transaction.atomic
    def wrapper(message, *args, **kwargs):
        try:
            conn = pymysql.connect(
                host=settings.DB_HOST,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                database=settings.DATABASES,
                charset='utf8mb4',
                cursorclass=DictCursor
            )
            conn.ping(reconnect=True)

            if not TelegramUsers.objects.filter(id=message.from_user.id).exists():
                user = TelegramUsers(
                    id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name,
                    is_staff=False,
                )
                user.save()
                time.sleep(1)

            user = TelegramUsers.objects.get(id=message.from_user.id)
            if user.is_blocked():
                Bot.send_message(message.from_user.id,
                                 "‼️Вы заблокированы ‼️\n")
                return None

            return func(message, *args, **kwargs)
        except Exception as ex:
            send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())

    return wrapper


class Console:
    botThread = None

    @staticmethod
    def set_webhook():
        Bot.remove_webhook()
        time.sleep(5)
        Bot.set_webhook(url=WEBHOOK_URL)

    @staticmethod
    @csrf_exempt
    def webhook(request):
        if request.method == "POST":
            json_string = request.body.decode("utf-8")
            update = telebot.types.Update.de_json(json_string)
            Bot.process_new_updates([update])
            return JsonResponse({"status": "ok"})

    @staticmethod
    @requires_staff
    def run(request):
        if Console.botThread is not None:
            if not Console.botThread.is_alive():
                Console.botThread = threading.Thread(target=Console.set_webhook())
                Console.botThread.start()
        else:
            Console.botThread = threading.Thread(target=Console.set_webhook())
            Console.botThread.start()
        print(f'Bot is now running in a separate thread.')
        return redirect('ZangerKZ:console')

    @staticmethod
    @requires_staff
    def stop(request):
        if Console.botThread is not None:
            if Console.botThread.is_alive():
                Bot.stop_polling()
        print(f'Bot is now stopping in a separate thread.')
        return redirect('ZangerKZ:console')

    @staticmethod
    def run_command(value, command):
        if value == 'terminal':
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
            return str(result.stdout), str(result.stderr)
        if value == 'mysql':
            try:
                with connection.cursor() as cursor:
                    cursor.execute(command)

                    result = cursor.fetchall()

                    result = '\n'.join(str(item) for item in result)
                    return str(result), None
            except Exception as ex:
                return None, str(ex)

    @staticmethod
    @requires_staff
    def clear(request):
        request.session['command_history'] = []
        request.session.modified = True
        return redirect('ZangerKZ:console')

    @staticmethod
    @requires_staff
    def set(request, value):
        request.session['command_line'] = value
        return redirect('ZangerKZ:console')

    @staticmethod
    @requires_staff
    def render(request):
        name = Bot.get_my_name().name
        context = {
            'bot_name': name
        }
        if 'command_line' not in request.session:
            request.session['command_line'] = 'terminal'

        if request.method == 'POST':
            command = request.POST.get('command')
            stdout, stderr = Console.run_command(request.session['command_line'], command)
            # сохраняем историю выполнения команд в сессии
            if 'command_history' not in request.session:
                request.session['command_history'] = []

            request.session['command_history'].append({
                'command': command,
                'stdout': stdout,
                'stderr': stderr,
            })
            request.session.modified = True

        return render(request, 'zangerkz/console.html', context)

    @staticmethod
    def error(request):
        return render(request, 'zangerkz/error.html')


@Bot.message_handler(commands=['start'])
@requires_db
def start(message):
    try:
        Bot.send_message(message.from_user.id,
                         "Привет! 🤖 Я - ZangerKZ, твой юридический помощник от KazNU! 🌐 \n"
                         "\n"
                         "Можешь задавать любые юридические вопросы. 💡\n"
                         "\n"
                         "Жду твои вопросы! 🗣",
                         reply_markup=menu(message))

    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


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
@requires_db
def start_new_dialog(message):
    try:
        user_id = message.from_user.id
        user = TelegramUsers.objects.get(id=user_id)
        user.clear_messages()
        content = "🤖 Привет! Я ZangerKZ. Чем я могу тебе помочь?"
        user.add_message("assistant", content)
        Bot.send_message(message.from_user.id, text=content, reply_markup=menu(message))

    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.callback_query_handler(func=lambda call: call.data == 'profile')
@Bot.message_handler(func=lambda message: message.text == '👤 Мой профиль')
@requires_db
def profile(message):
    try:
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
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.callback_query_handler(func=lambda call: call.data == 'positive')
@Bot.callback_query_handler(func=lambda call: call.data == 'negative')
@transaction.atomic
@requires_db
def save_review(call):
    try:
        user = TelegramUsers.objects.get(id=call.message.reply_to_message.from_user.id)

        review = Reviews(
            author=user,
            question=call.message.reply_to_message.text,
            answer=call.message.text,
            review=call.data)
        review.save()

        Bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=None)
        Bot.send_message(call.message.reply_to_message.from_user.id,
                         "Спасибо за ваш отзыв",
                         reply_markup=menu(call.message))
    except Exception as ex:
        send_error_for_admins(call, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


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
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())
        return "❗️ Системная ошибка ❗️"
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())
        return "❗️ Системная ошибка ❗️"


def load_text_from_files(file_paths):
    text = ""

    for file_path in file_paths:
        with open(file_path, "r", encoding="utf-8") as file:
            text += file.read() + "\n"

    return text


def send_error_for_admins(message, ex, method_name, error_details):
    user_id = None
    if message is not None:
        Bot.send_message(message.from_user.id,
                         "⚠️ Произошла непредвиденная ошибка, сообщение об ошибке уже отправлено модерации.\n"
                         "Подождите пару минут и повторите попытку.")
        user_id = message.from_user.id
    text_to_error_html(error_details)
    admins = TelegramUsers.objects.filter(is_staff=True)
    text = "❗️ Сообщение от системы ❗️\n" \
           f"User ID: {user_id}\n" \
           f"Method: {method_name}\n" \
           f"Error type: {type(ex).__name__}\n" \
           f"Error message: {str(ex)}\n"
    logger.error(text)
    for admin in admins:
        Bot.send_message(admin.id, text)
    print(text)


@Bot.message_handler(func=lambda message: True)
@requires_db
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
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


def text_to_error_html(error_details):
    try:
        app_templates_directory = os.path.join(settings.BASE_DIR, "ZangerKZ", 'templates')
        with open(app_templates_directory + "/zangerkz/error.html",
                  'w', encoding='utf-8') as file:
            file.write(str(error_details))
    except Exception as ex:
        logger.error(ex)
