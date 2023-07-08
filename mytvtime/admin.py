from django.contrib import admin

from .models import Show, Watchlist, NextEpisode
# Register your models here.

admin.site.register(Show)
admin.site.register(Watchlist)
admin.site.register(NextEpisode)