from django.contrib import admin

from ANTIBOT.models import TelegramUsers, Channels, Tokens


# Register your models here.
class TelegramUsersAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'blocked', 'is_staff')
    list_filter = ('blocked', 'is_staff', )


class ChannelsAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


class TokensAdmin(admin.ModelAdmin):
    list_display = ('telegram_bot_token', )


admin.site.register(TelegramUsers, TelegramUsersAdmin)
admin.site.register(Channels, ChannelsAdmin)
admin.site.register(Tokens, TokensAdmin)
