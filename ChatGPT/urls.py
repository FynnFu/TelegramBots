from django.urls import path
from .views import Console

app_name = "ChatGPT"

urlpatterns = [
    path('console/', Console.render, name='console'),
    path('run/', Console.run, name='run'),
    path('stop/', Console.stop, name='stop'),
    path('error/', Console.error, name='error')
]
