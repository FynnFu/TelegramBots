from django.db import models


# Create your models here.
class TelegramUsers(models.Model):
    id = models.BigIntegerField(primary_key=True, null=False, unique=True, verbose_name="ID пользователя")
    username = models.CharField(null=True, blank=True, max_length=250, verbose_name="Имя пользователя")
    first_name = models.CharField(null=True, blank=True, max_length=250, verbose_name="Имя")
    last_name = models.CharField(null=True, blank=True, max_length=250, verbose_name="Фамилия")
    blocked = models.BooleanField(default=False, verbose_name="Заблокирован")
    is_staff = models.BooleanField(default=False, verbose_name="Персонал")

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


class Channels(models.Model):
    id = models.IntegerField(primary_key=True, verbose_name='ID канала')
    name = models.CharField(max_length=250, verbose_name='Имя канала')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Канал"
        verbose_name_plural = "Каналы"
