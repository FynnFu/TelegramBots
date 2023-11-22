from django.contrib import admin

from ANTIBOT.models import TelegramUsers, Channels


# Register your models here.
class TelegramUsersAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'blocked', 'is_staff')
    list_filter = ('blocked', 'is_staff', )


class ChannelsAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


admin.site.register(TelegramUsers, TelegramUsersAdmin)
admin.site.register(Channels, ChannelsAdmin)
