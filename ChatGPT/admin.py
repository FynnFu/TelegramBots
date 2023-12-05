from django.contrib import admin
from ChatGPT.models import TelegramUsers, Promocodes, Channels, GPTModels, Prices, Tips, Tokens


class TelegramUsersAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'blocked', 'is_staff', 'RPD', 'RPD_BONUS',
                    'IPD', 'referrer', 'referrals')
    list_filter = ('blocked', 'is_staff', )


class PromocodesAdmin(admin.ModelAdmin):
    list_display = ('code', 'NOR')
    list_filter = ('NOR', )


class ChannelsAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'url')


class GPTModelsAdmin(admin.ModelAdmin):
    list_display = ('name',)


class PricesAdmin(admin.ModelAdmin):
    list_display = ('description', 'value', 'price')


class TipsAdmin(admin.ModelAdmin):
    list_display = ('amount', )


class TokensAdmin(admin.ModelAdmin):
    list_display = ('openai_api_key', 'telegram_bot_token', )


# Register your models here.
admin.site.register(TelegramUsers, TelegramUsersAdmin)
admin.site.register(Promocodes, PromocodesAdmin)
admin.site.register(Channels, ChannelsAdmin)
admin.site.register(GPTModels, GPTModelsAdmin)
admin.site.register(Prices, PricesAdmin)
admin.site.register(Tips, TipsAdmin)
admin.site.register(Tokens, TokensAdmin)
