# Generated by Django 4.2.3 on 2023-07-14 08:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mytvtime', '0006_rename_updated_at_nextepisode_trakt_updated_at_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='nextepisode',
            name='timestamp',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='show',
            name='timestamp',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='watched',
            name='timestamp',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='watchlist',
            name='timestamp',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
