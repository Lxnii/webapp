# Generated by Django 4.2.3 on 2023-07-05 05:28

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mytvtime', '0002_alter_show_tmdb_id'),
    ]

    operations = [
        migrations.DeleteModel(
            name='UserProfile',
        ),
    ]
