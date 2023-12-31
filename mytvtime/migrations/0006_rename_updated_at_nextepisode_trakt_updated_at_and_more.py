# Generated by Django 4.2.3 on 2023-07-14 07:00

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('mytvtime', '0005_alter_show_status_alter_show_year'),
    ]

    operations = [
        migrations.RenameField(
            model_name='nextepisode',
            old_name='updated_at',
            new_name='trakt_updated_at',
        ),
        migrations.AddField(
            model_name='nextepisode',
            name='timestamp',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='show',
            name='timestamp',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='show',
            name='trakt_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
