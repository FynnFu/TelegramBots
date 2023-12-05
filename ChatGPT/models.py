import json

from django.db import models


class GPTModels(models.Model):
    name = models.CharField(max_length=250, verbose_name="Название")
    slug = models.CharField(max_length=250, verbose_name="Slug")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Модель"
        verbose_name_plural = "Модели"


class TelegramUsers(models.Model):
    id = models.BigIntegerField(primary_key=True, null=False, unique=True, verbose_name="ID пользователя")
    username = models.CharField(null=True, blank=True, max_length=250, verbose_name="Имя пользователя")
    first_name = models.CharField(null=True, blank=True, max_length=250, verbose_name="Имя")
    last_name = models.CharField(null=True, blank=True, max_length=250, verbose_name="Фамилия")
    blocked = models.BooleanField(default=False, verbose_name="Заблокирован")
    is_staff = models.BooleanField(default=False, verbose_name="Персонал")
    RPD = models.IntegerField(verbose_name="Количество ежедневных запросов")
    RPD_BONUS = models.IntegerField(verbose_name="Количество бонусных запросов")
    IPD = models.IntegerField(verbose_name="Количество ежедневных изображений")
    referrer = models.ForeignKey('self',
                                 on_delete=models.CASCADE,
                                 null=True,
                                 blank=True,
                                 verbose_name="Реферер")
    referrals = models.IntegerField(verbose_name="Количество рефералов")
    messages = models.TextField(default='[]', verbose_name="Сообщения")
    model = models.ForeignKey(GPTModels, on_delete=models.CASCADE, verbose_name="Модель")

    def set_rpd(self, quantity):
        self.RPD = quantity
        self.save()

    def set_rpd_bonus(self, quantity):
        self.RPD_BONUS = quantity
        self.save()

    def set_ipd(self, quantity):
        self.IPD = quantity
        self.save()

    def set_referrer(self, referrer):
        self.referrer = referrer
        self.save()

    def set_model(self, model):
        self.model = model
        self.save()

    def get_rpd(self):
        return self.RPD

    def get_rpd_bonus(self):
        return self.RPD_BONUS

    def get_ipd(self):
        return self.IPD

    def get_referral(self):
        return self.referrals

    def get_referrer(self):
        return self.referrer

    def get_messages(self):
        messages = json.loads(self.messages)
        return messages

    def get_model(self):
        return self.model

    def clear_messages(self):
        self.messages = '[]'
        self.save()

    def remove_rpd(self, quantity):
        self.RPD -= quantity
        self.save()

    def remove_rpd_bonus(self, quantity):
        self.RPD_BONUS -= quantity
        self.save()

    def remove_ipd(self, quantity):
        self.IPD -= quantity
        self.save()

    def add_rpd(self, quantity):
        self.RPD += quantity
        self.save()

    def add_rpd_bonus(self, quantity):
        self.RPD_BONUS += quantity
        self.save()

    def add_ipd(self, quantity):
        self.IPD += quantity
        self.save()

    def add_referral(self):
        self.referrals += 1
        self.save()

    def add_message(self, role, content):
        messages = json.loads(self.messages)
        messages.append({"role": role, "content": content})
        self.messages = json.dumps(messages)
        self.save()

    def ban(self):
        self.blocked = True
        self.save()

    def unban(self):
        self.blocked = False
        self.save()

    def is_blocked(self):
        return self.blocked

    def __str__(self):
        return str(self.id)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"


class Promocodes(models.Model):
    code = models.CharField(max_length=16, verbose_name="Код")
    NOR = models.IntegerField(verbose_name="Количество запросов")

    def __str__(self):
        return self.code

    class Meta:
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоды"


class Channels(models.Model):
    id = models.BigIntegerField(verbose_name="ID канала", primary_key=True)
    name = models.CharField(max_length=250, verbose_name="Название канала")
    url = models.URLField()

    def __str__(self):
        return str(self.name)

    class Meta:
        verbose_name = "Канал"
        verbose_name_plural = "Каналы"


class Prices(models.Model):
    description = models.CharField(max_length=250, verbose_name="Описание")
    price = models.IntegerField(verbose_name="Цена")
    value = models.IntegerField(verbose_name="Количество")
    top = models.BooleanField(default=False, verbose_name="В топе")

    def __str__(self):
        return self.description

    def in_top(self):
        return self.top

    class Meta:
        verbose_name = "Цена"
        verbose_name_plural = "Цены"


class Tips(models.Model):
    amount = models.IntegerField(verbose_name="Количество")

    def __str__(self):
        return str(self.amount)

    class Meta:
        verbose_name = "Чаевые"
        verbose_name_plural = "Чаевые"


class Tokens(models.Model):
    openai_api_key = models.CharField(max_length=2000, verbose_name="OpenAI API key")
    telegram_bot_token = models.CharField(max_length=2000, verbose_name="Telegram Bot Token")

    class Meta:
        verbose_name = "Ключ"
        verbose_name_plural = "Ключи"
