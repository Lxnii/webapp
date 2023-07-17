import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webapp.settings') 
django.setup()

from mytvtime.views import auto_update_all_database_shows

auto_update_all_database_shows()
