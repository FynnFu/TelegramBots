from django.contrib import admin

from ZangerKZ.models import TelegramUsers, Reviews, Tokens


# Register your models here.
class TelegramUsersAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'blocked', 'is_staff')
    list_filter = ('blocked', 'is_staff', )


class ReviewsAdmin(admin.ModelAdmin):
    list_display = ('author', 'review')
    list_filter = ('review', )


class TokensAdmin(admin.ModelAdmin):
    list_display = ('openai_api_key', 'telegram_bot_token', )


admin.site.register(TelegramUsers, TelegramUsersAdmin)
admin.site.register(Reviews, ReviewsAdmin)
admin.site.register(Tokens, TokensAdmin)
