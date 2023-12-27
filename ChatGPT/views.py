import inspect
import json
import os
import subprocess
import threading
import logging
import time
import traceback

import pymysql
import telebot
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.db import transaction
from django.contrib.sites.models import Site
from django.shortcuts import render, redirect
from openai import OpenAI, RateLimitError
from pymysql.cursors import DictCursor
from telebot import types
from telebot.types import BotCommand, LabeledPrice
from dotenv import load_dotenv
from telegram import constants
from telegram.helpers import escape_markdown

from TelegramBots import settings
from ChatGPT.models import TelegramUsers, Promocodes, Channels, GPTModels, Prices, Tips

load_dotenv()

logger = logging.getLogger('django')

try:
    URL = Site.objects.get_current().domain + "/chatgpt"
except Exception as e:
    URL = "https://example.com/chatgpt"
    logger.error(e)

WEBHOOK_URL = URL + "/webhook/"

TOKEN = os.getenv("TOKEN_CHATGPT")
API_KEY = os.getenv("API_KEY_CHATGPT")

Bot = telebot.TeleBot(TOKEN)

client = OpenAI(api_key=API_KEY)

commands = [
    BotCommand('start', '🔄 Запустить/перезапустить бота'),
    BotCommand('ref', "📨 Приглашение"),
    BotCommand('promocode', "🔑 Ввести промокод"),
    BotCommand('start_new_dialog', "➕ Начать новый диалог"),
]

Bot.set_my_commands(commands)


def requires_staff(func):
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.is_staff:
                return func(request, *args, **kwargs)

        return redirect(f'{reverse("admin:login")}?next={request.path}')

    return wrapper


class Console:
    botThread = None

    @staticmethod
    def set_webhook():
        Bot.remove_webhook()
        time.sleep(5)
        print(WEBHOOK_URL)
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
    def status():
        is_bot = Bot.get_me().is_bot
        name = Bot.get_me().username

        text = f"Bot({name}) is bot: {is_bot}\n"
        return text

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
        return redirect('ChatGPT:console')

    @staticmethod
    @requires_staff
    def stop(request):
        if Console.botThread is not None:
            if Console.botThread.is_alive():
                Bot.delete_webhook()
        print(f'Bot is now stopping in a separate thread.')
        return redirect('ChatGPT:console')

    @staticmethod
    def run_command(value, command):
        if value == 'terminal':
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
            return str(result.stdout), str(result.stderr)
        if value == 'mysql':
            try:
                with pymysql.connect(
                        host=settings.DB_HOST,
                        user=settings.DB_USER,
                        password=settings.DB_PASSWORD,
                        database=settings.DB_NAME,
                        charset='utf8mb4',
                        cursorclass=DictCursor
                ) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(command)

                        result = cursor.fetchall()

                        result = '\n'.join(str(item) for item in result)
                        return str(result), None
            except pymysql.Error as ex:
                return None, str(ex)
            except Exception as ex:
                return None, str(ex)

    @staticmethod
    @requires_staff
    def clear(request):
        request.session['command_history'] = []
        request.session.modified = True
        return redirect('ChatGPT:console')

    @staticmethod
    @requires_staff
    def set(request, value):
        request.session['command_line'] = value
        return redirect('ChatGPT:console')

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

        return render(request, 'chatgpt/console.html', context)

    @staticmethod
    def error(request):
        return render(request, 'chatgpt/error.html')


def requires_subscription(func):
    @Bot.callback_query_handler(func=lambda call: call.data == 'check_subscribe')
    @transaction.atomic
    def wrapper(message, *args, **kwargs):
        try:
            with pymysql.connect(
                    host=settings.DB_HOST,
                    user=settings.DB_USER,
                    password=settings.DB_PASSWORD,
                    database=settings.DB_NAME,
                    charset='utf8mb4',
                    cursorclass=DictCursor
            ) as connection:
                connection.ping(reconnect=True)

                if not TelegramUsers.objects.filter(id=message.from_user.id).exists():
                    user = TelegramUsers(
                        id=message.from_user.id,
                        username=message.from_user.username,
                        first_name=message.from_user.first_name,
                        last_name=message.from_user.last_name,
                        blocked=False,
                        is_staff=False,
                        RPD=5,
                        RPD_BONUS=0,
                        IPD=1,
                        referrer=None,
                        referrals=0,
                        messages='[]',
                        model=GPTModels.objects.get(name="GPT-4")
                    )
                    user.save()
                    time.sleep(1)

                user = TelegramUsers.objects.get(id=message.from_user.id)
                if user.is_blocked():
                    Bot.send_message(message.from_user.id,
                                     "‼️Вы заблокированы ‼️\n"
                                     "За подробностями писать @FynnFu")
                    return None

                reply_message_id = None
                if type(message) == types.Message:
                    reply_message_id = message.message_id
                elif type(message) == types.CallbackQuery:
                    reply_message_id = message.message.message_id

                validation = True
                channels = Channels.objects.all()
                markup = types.InlineKeyboardMarkup()

                for channel in channels:
                    chat_member = Bot.get_chat_member(channel.id, message.from_user.id)
                    if not (chat_member.status == "member" or
                            chat_member.status == "administrator" or
                            chat_member.status == "creator"):
                        validation = False
                        markup.add(
                            types.InlineKeyboardButton(text=channel.name, url=channel.url)
                        )

                markup.add(
                    types.InlineKeyboardButton(text="✅ Я подписался", callback_data='check_subscribe')
                )

                if validation:
                    return func(message, *args, **kwargs)
                else:
                    if type(message) == types.CallbackQuery:
                        if message.data == 'check_subscribe':
                            Bot.answer_callback_query(callback_query_id=message.id,
                                                      show_alert=True,
                                                      text='Подпишитесь на все каналы!')
                        else:
                            Bot.send_message(message.from_user.id,
                                             "Для того, чтобы пользоваться ботом, вам необходимо подписаться на "
                                             "канал.\n"
                                             "После подписки, нажмите на соответствующую кнопку.",
                                             reply_markup=markup,
                                             reply_to_message_id=reply_message_id)
                    else:
                        Bot.send_message(message.from_user.id,
                                         "Для того, чтобы пользоваться ботом, вам необходимо подписаться на канал.\n"
                                         "После подписки, нажмите на соответствующую кнопку.",
                                         reply_markup=markup,
                                         reply_to_message_id=reply_message_id)
                    return None
        except Exception as ex:
            send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())

    return wrapper


@Bot.message_handler(commands=['start'])
@transaction.atomic
@requires_subscription
def start(message):
    try:
        Bot.send_message(message.from_user.id,
                         "Привет! 🤖 Я - ChatGPT, твой собеседник от OpenAI! 🌐 \n"
                         "\n"
                         "Можешь задавать любые вопросы, от математики до творчества. 💡\n"
                         "\n"
                         "Любишь программирование? Я тоже! 🖥️ Готов помочь с кодом. \n"
                         "\n"
                         "Пиши свои идеи, и я создам текст для них! ✨\n"
                         "\n"
                         "Освежи в памяти материалы школы или просто поболтаем. 🗣️\n"
                         "\n"
                         "Жду твои вопросы и идеи! 🚀",
                         reply_markup=menu(message))
        if type(message) == types.Message:
            start_param = message.text[len('/start '):]
            if start_param != '' and '/start ' in message.text:
                ref(message)
        elif type(message) == types.CallbackQuery:
            start_param = message.message.reply_to_message.text[len('/start '):]
            if start_param != '' and '/start ' in message.message.reply_to_message.text:
                ref(message.message.reply_to_message)
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.message_handler(commands=['ref'])
@transaction.atomic
@requires_subscription
def ref(message):
    try:
        user = TelegramUsers.objects.get(id=message.from_user.id)
        if user.referrer is None:
            referrer_id = message.text.split()[1:]
            if len(referrer_id) == 0:
                Bot.send_message(message.from_user.id,
                                 "📨 Введите автора приглашения\n"
                                 "\n"
                                 "/ref ||тут id автора||",
                                 reply_markup=menu(message),
                                 parse_mode='MarkdownV2')
            elif len(referrer_id) == 1 and int(referrer_id[0]) == message.from_user.id:
                Bot.send_message(message.from_user.id,
                                 "😜 А ты умён, но автором приглашения должен быть кто-то другой",
                                 reply_markup=menu(message))
            elif len(referrer_id) == 1 and TelegramUsers.objects.filter(id=referrer_id[0]).exists():
                referrer = TelegramUsers.objects.get(id=referrer_id[0])
                user.set_referrer(referrer)
                user.add_rpd_bonus(3)

                referrer.add_rpd_bonus(3)
                referrer.add_referral()

                Bot.send_message(message.from_user.id, "🎉 Приглашение активировано\n"
                                                       "🎁 Вам начислено 3 бонусных запроса\n",
                                 reply_markup=menu(message))
            else:
                Bot.send_message(message.from_user.id, "🧐 Автор приглашения не найден", reply_markup=menu(message))
        else:
            Bot.send_message(message.from_user.id, "❌ Вы уже использовали приглашение", reply_markup=menu(message))
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.callback_query_handler(func=lambda call: call.data == 'profile')
@Bot.message_handler(func=lambda message: message.text == '👤 Мой профиль')
@requires_subscription
def profile(message):
    try:
        user = TelegramUsers.objects.get(id=message.from_user.id)

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(text="✨ Купить запросы", callback_data='gpt_premium')
        )
        markup.add(
            types.InlineKeyboardButton(text="🤝 Пригласить друга", callback_data='invite_friend')
        )
        markup.add(
            types.InlineKeyboardButton(text="🔑 Ввести промокод", callback_data='enter_promocode')
        )
        text = f"👤: {user.first_name} {user.last_name} ({user.username})\n" \
               f"\n" \
               f"💬: Доступно запросов для ChatGPT-4:\n" \
               f"    🎁 Бонусных: {user.RPD_BONUS}\n" \
               f"    🔄 Ежедневных: {user.RPD}\n" \
               f"\n" \
               f"🖼: Доступно изображений для DALL-E:\n" \
               f"    🔄 Ежедневных: {user.IPD}\n" \
               f"\n"f"Запросы в ChatGPT нужны, чтобы задавать вопросы.\n" \
               f"Бесплатно даём 5 запросов ежедневно, восстанавливаются в 00:00 по Алмате.\n" \
               f"\n" \
               f"1️⃣ Вы можете купить GPT запросы и не париться о лимитах.\n" \
               f"2️⃣ Вы можете пригласить друга, и Вы и он получите по 3 бонусных запроса.\n" \
               f"3️⃣ Вы можете воспользоваться промокодом, если он у вас есть.\n"

        if type(message) == types.Message:
            Bot.send_message(user.id, text=text, reply_markup=markup)
        elif type(message) == types.CallbackQuery:
            Bot.edit_message_text(
                chat_id=message.message.chat.id,
                message_id=message.message.message_id,
                text=text,
                reply_markup=markup
            )
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.callback_query_handler(func=lambda call: call.data == 'invite_friend')
@requires_subscription
def invite_friend(call):
    try:
        user = TelegramUsers.objects.get(id=call.from_user.id)
        ref_command = f"/ref {user.id}"
        ref_url = f"https://t.me/free4gpt_bot?start={user.id}"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("📝 Поделиться кодом", url=f"t.me/share/url?url={ref_command}")
        )
        markup.add(
            types.InlineKeyboardButton("📝 Поделиться ссылкой", url=f"t.me/share/url?url={ref_url}")
        )
        # markup.add(
        #     types.InlineKeyboardButton("⬅️ Вернуться назад", callback_data='profile')
        # )
        Bot.send_message(
            chat_id=call.message.chat.id,
            text=f"👥 Вы пригласили: {user.referrals} человек(-а)\n"
                 f"Ваша команда для приглашения:\n"
                 f"Код:\n"
                 f"{ref_command}\n"
                 f"\n"
                 f"Ссылка:\n"
                 f"{ref_url} \n"
                 f"\n"
                 f"Для того чтобы использовать команду, пользователь должен авторизоваться с помощью команды /start.",
            reply_markup=markup)
    except Exception as ex:
        send_error_for_admins(call, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.message_handler(commands=['promocode'])
@Bot.callback_query_handler(func=lambda call: call.data == 'enter_promocode')
@requires_subscription
def enter_promocode(message):
    try:
        text = f"🔑 Для активации промокода введите команду:\n" \
               f"\n" \
               f"/promocode ||тут промокод||"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("⬅️ Вернуться назад", callback_data='profile')
        )
        if type(message) == types.Message:
            code = message.text.split()[1:]
            if len(code) == 0:
                Bot.send_message(message.from_user.id, text, reply_markup=menu(message), parse_mode='MarkdownV2')
            elif len(code) == 1 and Promocodes.objects.filter(code=code[0]).exists():
                promocode = Promocodes.objects.get(code=code[0])
                user = TelegramUsers.objects.get(id=message.from_user.id)
                user.add_rpd_bonus(promocode.NOR)

                promocode.delete()
                Bot.send_message(message.from_user.id, f"✅ Промокод активирован", reply_markup=menu(message))
            else:
                Bot.send_message(message.from_user.id, f"❌ Промокод не найден", reply_markup=menu(message))
        elif type(message) == types.CallbackQuery:
            Bot.edit_message_text(
                chat_id=message.message.chat.id,
                message_id=message.message.message_id,
                text=text,
                reply_markup=markup,
                parse_mode='MarkdownV2'
            )
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@requires_subscription
def menu(message):
    try:
        # user_id = message.from_user.id
        # user = TelegramUsers.objects.get(id=user_id)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

        markup.add(
            types.KeyboardButton("➕ Начать новый диалог"),
            types.KeyboardButton("✨ GPT запросы")
        )
        markup.add(
            types.KeyboardButton("🚀 Midjourney бот"),
            types.KeyboardButton("🤖 Выбрать модель")
        )
        markup.add(
            types.KeyboardButton("👤 Мой профиль")
        )
        return markup
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())
        return None


@Bot.message_handler(commands=['start_new_dialog'])
@Bot.callback_query_handler(func=lambda call: call.data == 'start_new_dialog')
@Bot.message_handler(func=lambda message: message.text == '➕ Начать новый диалог')
@requires_subscription
def start_new_dialog(message):
    try:
        user_id = message.from_user.id
        user = TelegramUsers.objects.get(id=user_id)
        user.clear_messages()
        content = "🤖 Привет! Я ChatGPT. Чем я могу тебе помочь?"
        user.add_message("assistant", content)
        Bot.send_message(message.from_user.id, text=content, reply_markup=menu(message))

    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.callback_query_handler(func=lambda call: call.data == 'gpt_premium')
@Bot.message_handler(func=lambda message: message.text == '✨ GPT запросы')
@requires_subscription
def gpt_premium(message):
    try:
        user_id = message.from_user.id
        user = TelegramUsers.objects.get(id=user_id)
        user.clear_messages()
        content = "👇 Выберите количество запросов\n" \
                  "\n" \
                  "🔹 Запросы никогда не сгорают, можно хранить сколько угодно по времени\n" \
                  "🔸 Запросы будут добавлены к бонусным запросам и вы сможете их использовать сразу после оплаты\n"
        markup = types.InlineKeyboardMarkup()

        prices = Prices.objects.all()

        for price in prices:
            text = f"{price.description} - {price.price} ₽"
            if price.in_top():
                text = "🔥 " + text
            markup.add(
                types.InlineKeyboardButton(text=text,
                                           callback_data=f"price_selected:{price.price}")
            )

        Bot.send_message(message.from_user.id, text=content, reply_markup=markup)

    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.callback_query_handler(lambda call: call.data.startswith('price_selected:'))
def process_price_selected(call):
    try:
        price = call.data.split(':')[-1]
        price_obj = Prices.objects.get(price=price)
        tips = Tips.objects.all()
        payload = {
            "user_id": call.from_user.id,
            "value": price_obj.value
        }

        Bot.send_invoice(
            call.from_user.id,
            "GPT-4 запросы",
            description=price_obj.description,
            provider_token=os.getenv("TOKEN_YOOKASSA"),
            currency="RUB",
            prices=[
                LabeledPrice(
                    label=price_obj.description,
                    amount=price_obj.price * 100
                )
            ],
            max_tip_amount=500 * 100,
            suggested_tip_amounts=[tip.amount * 100 for tip in tips],
            start_parameter="free4gpt_bot",
            provider_data=None,
            photo_url="https://static2.tgstat.ru/channels/_0/dd/dd151ce9a6bc922029428ad2b61936ad.jpg",
            photo_size=30000,
            photo_width=640,
            photo_height=640,
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            send_phone_number_to_provider=False,
            send_email_to_provider=False,
            is_flexible=False,
            disable_notification=False,
            protect_content=False,
            reply_to_message_id=None,
            allow_sending_without_reply=True,
            reply_markup=None,
            invoice_payload=json.dumps(payload)
        )
    except Exception as ex:
        send_error_for_admins(call, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.pre_checkout_query_handler(func=lambda query: True)
def pre_checkout(pre_checkout_query):
    try:
        Bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    except Exception as ex:
        send_error_for_admins(pre_checkout_query, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.message_handler(content_types=['successful_payment'])
def process_successful_payment(message):
    try:
        invoice_payload = message.successful_payment.invoice_payload
        payload = json.loads(invoice_payload)
        user = TelegramUsers.objects.get(id=payload['user_id'])
        user.add_rpd_bonus(int(payload['value']))
        Bot.send_message(message.from_user.id,
                         f"🥳 Поздравляю, оплата прошла успешна.\n"
                         f"\n"
                         f"✨ Ваши запросы уже начислены Вам на аккаунт, наслаждайтесь всеми возможностями GPT-4")
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


def generate_gpt_response(prompt, model, message):
    try:
        if model == 'gpt-4-0314':
            Bot.send_chat_action(message.from_user.id, 'typing')
            completion = client.chat.completions.create(
                model=f"{model}",
                messages=prompt
            )
            return completion.choices[0].message.content

        if model == 'gpt-3.5-turbo':
            Bot.send_chat_action(message.from_user.id, 'typing')
            completion = client.chat.completions.create(
                model=f"{model}",
                messages=prompt
            )
            return completion.choices[0].message.content

    except RateLimitError as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())
        return "❗️ Системная ошибка ❗️"
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())
        return "❗️ Системная ошибка ❗️"


@Bot.message_handler(func=lambda message: message.text == '🚀 Midjourney бот')
@requires_subscription
def midjourney(message):
    try:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="🚀 Midjourney", url="https://t.me/Midjorai_bot"))
        Bot.send_message(message.from_user.id,
                         "Для генерации изображения перейдите в бота Midjourney\n"
                         "Достаточно кликнуть на кнопку под этим сообщением.",
                         reply_markup=markup)
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.message_handler(func=lambda message: message.text == '🤖 Выбрать модель')
@requires_subscription
def choose_model(message):
    try:
        user_id = message.from_user.id
        markup = types.InlineKeyboardMarkup()
        models = GPTModels.objects.all()
        user = TelegramUsers.objects.get(id=user_id)
        for model in models:
            model_name = model.name
            if model == user.model:
                model_name = f"✅ {model.name} ✅"

            markup.add(
                types.InlineKeyboardButton(
                    text=f"{model_name}",
                    callback_data=model.slug
                )
            )
        if type(message) == types.Message:
            Bot.send_message(message.from_user.id,
                             "От выбранной модели зависит скорость и качество ответа."
                             "\n"
                             "Выберите одну модель из списка:\n",
                             reply_markup=markup)
        return markup
    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


@Bot.callback_query_handler(func=lambda call: True)
def set_user_model(call):
    try:
        models = GPTModels.objects.all()
        user_id = call.from_user.id
        user = TelegramUsers.objects.get(id=user_id)
        for model in models:
            if call.data == model.slug:
                if user.model != model:
                    user.set_model(model)
                    Bot.edit_message_reply_markup(call.from_user.id, call.message.message_id,
                                                  reply_markup=choose_model(call))
    except Exception as ex:
        send_error_for_admins(call, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


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
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(text="Страница с ошибкой", url=f"{URL}{reverse(f'ChatGPT:error')}")
    )
    for admin in admins:
        Bot.send_message(admin.id, text, reply_markup=markup)
    print(text)


@Bot.message_handler(func=lambda message: True)
@requires_subscription
def handle_messages(message):
    try:
        user_id = message.from_user.id
        user = TelegramUsers.objects.get(id=user_id)

        if message.text == "➕ Начать новый диалог" or message.text == "/start_new_dialog" \
                or message.text == "✨ GPT запросы" \
                or message.text == "🚀 Midjourney бот" \
                or message.text == "🤖 Выбрать модель" \
                or message.text == "👤 Мой профиль" \
                or message.text == "/ref" \
                or message.text == "/promocode":
            return
        else:
            if user.get_rpd_bonus() > 0 or user.get_rpd() > 0:
                thinking_message = Bot.send_message(message.from_user.id,
                                                    "🧠 Думаю над ответом...",
                                                    reply_to_message_id=message.message_id)

                user.add_message("user", message.text)

                gpt_response = generate_gpt_response(user.get_messages(),
                                                     user.get_model().slug,
                                                     message)

                # characters = {'_', '*', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'}
                #
                # for character in characters:
                #     gpt_response = gpt_response.replace(character, f'\\{character}')

                gpt_response = escape_markdown(gpt_response, version=2, entity_type="code")

                if user.get_rpd_bonus() > 0:
                    user.remove_rpd_bonus(1)
                elif user.get_rpd() > 0:
                    user.remove_rpd(1)

                if len(gpt_response) > 4095:
                    for x in range(0, len(gpt_response), 4095):
                        Bot.edit_message_text(chat_id=message.from_user.id,
                                              message_id=thinking_message.message_id,
                                              text=gpt_response[x:x + 4095], )
                        # parse_mode=constants.ParseMode.MARKDOWN_V2)
                else:
                    Bot.edit_message_text(chat_id=message.from_user.id,
                                          message_id=thinking_message.message_id,
                                          text=gpt_response, )
                    # parse_mode=constants.ParseMode.MARKDOWN_V2)

                user.add_message("assistant", gpt_response)

            else:
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton(text="✨ Купить запросы", callback_data='gpt_premium')
                )
                markup.add(
                    types.InlineKeyboardButton(text="🤝 Пригласить друга", callback_data='invite_friend')
                )
                Bot.send_message(message.from_user.id,
                                 "У Вас закончились запросы 😢\n"
                                 "\n"
                                 "Не беда, вы можете купить их или пригласить друга и получить бонусные запросы",
                                 reply_markup=markup)

    except Exception as ex:
        send_error_for_admins(message, ex, inspect.currentframe().f_code.co_name, traceback.format_exc())


def text_to_error_html(error_details):
    try:
        app_templates_directory = os.path.join(settings.BASE_DIR, "ChatGPT", 'templates')
        with open(app_templates_directory + "/chatgpt/error.html",
                  'w', encoding='utf-8') as file:
            file.write(str(error_details))
    except Exception as ex:
        logger.error(ex)
