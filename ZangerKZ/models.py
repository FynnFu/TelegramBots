import json

from django.db import models


class TelegramUsers(models.Model):
    id = models.BigIntegerField(primary_key=True, null=False, unique=True, verbose_name="ID пользователя")
    username = models.CharField(null=True, blank=True, max_length=250, verbose_name="Имя пользователя")
    first_name = models.CharField(null=True, blank=True, max_length=250, verbose_name="Имя")
    last_name = models.CharField(null=True, blank=True, max_length=250, verbose_name="Фамилия")
    blocked = models.BooleanField(default=False, verbose_name="Заблокирован")
    is_staff = models.BooleanField(default=False, verbose_name="Персонал")
    messages = models.TextField(default='[]')

    def get_messages(self):
        messages = json.loads(self.messages)
        return messages

    def clear_messages(self):
        self.messages = '[]'
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


class Reviews(models.Model):
    author = models.ForeignKey(TelegramUsers, on_delete=models.CASCADE)
    question = models.TextField(default='')
    answer = models.TextField(default='')
    review = models.CharField(max_length=250)

    def __str__(self):
        return str(self.author.id)

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"

