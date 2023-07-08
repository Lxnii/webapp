from django.urls import path
from . import views

app_name = 'mytvtime'

urlpatterns = [
    path('', views.index, name='index'),
    path('search/', views.search_results, name='search_results'),
    path('add_to_watchlist/<int:trakt_id>/', views.add_show_to_watchlist, name='add_to_watchlist'),
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('get_watching_shows/', views.get_watching_shows),
    path('remove_from_watchlist/', views.remove_show_from_watchlist, name='remove_from_watchlist'),
]
