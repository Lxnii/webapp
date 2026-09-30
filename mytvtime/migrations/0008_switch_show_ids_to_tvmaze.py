"""Switch the show/episode identifiers from Trakt ids to TVmaze ids.

The rename operations below are plain column renames, so the *values* are still
the old Trakt ids when remap_ids_to_tvmaze() runs. That function rewrites them
(and the referencing rows) to the TVmaze ids resolved from each show's IMDb id,
using TVmaze's /lookup/shows endpoint plus a name search for the two shows
TVmaze has no IMDb id for.
"""
from django.db import migrations


# old Trakt id -> TVmaze id, resolved on 2026-09-30 from db.sqlite3.
# 19 rows matched by IMDb id via GET /lookup/shows?imdb=... and 2 by
# GET /search/shows?q=<title> (Ling Cage, SHAMAN KING FLOWERS).
MAPPING = {
    1420: 919,
    30850: 1905,
    41793: 305,
    97548: 4201,
    97792: 4270,
    131598: 41469,
    150378: 79529,
    150900: 33352,
    154574: 44778,
    154997: 44933,
    155619: 45302,
    158594: 48450,
    164989: 49302,
    169972: 53277,
    188929: 63236,
    190742: 59698,
    193922: 60920,
    198111: 67396,
    198225: 69956,
    200782: 65895,
    208128: 73278,
}

# Keeps the temporary ids well clear of both the Trakt and TVmaze id ranges.
TEMP_OFFSET = 100000000


def remap_ids_to_tvmaze(apps, schema_editor):
    Show = apps.get_model('mytvtime', 'Show')
    Season = apps.get_model('mytvtime', 'Season')
    Watchlist = apps.get_model('mytvtime', 'Watchlist')
    NextEpisode = apps.get_model('mytvtime', 'NextEpisode')
    ShowUser = Show.users.through  # auto-created ManyToMany table

    current_ids = set(Show.objects.values_list('tvmaze_id', flat=True))
    if not current_ids:
        return  # fresh database, nothing to remap
    if current_ids == set(MAPPING.values()):
        return  # already remapped

    unmapped = sorted(current_ids - set(MAPPING))
    if unmapped:
        raise RuntimeError(
            'Cannot remap to TVmaze ids: no TVmaze id known for existing primary keys '
            f'{unmapped}. Run Show.objects.filter(imdb_id=...) lookups against '
            'https://api.tvmaze.com/lookup/shows and extend MAPPING in this migration.'
        )

    # Two passes so that a new id can never collide with an id that has not
    # been moved yet. Foreign keys in SQLite are DEFERRABLE INITIALLY DEFERRED,
    # so rows may reference a parent id that only exists again at commit time.
    for old_id in sorted(MAPPING):
        temp_id = old_id + TEMP_OFFSET
        Show.objects.filter(tvmaze_id=old_id).update(tvmaze_id=temp_id)
        Season.objects.filter(show_id=old_id).update(show_id=temp_id)
        Watchlist.objects.filter(show_id=old_id).update(show_id=temp_id)
        NextEpisode.objects.filter(show_id=old_id).update(show_id=temp_id)
        ShowUser.objects.filter(show_id=old_id).update(show_id=temp_id)

    for old_id, new_id in MAPPING.items():
        temp_id = old_id + TEMP_OFFSET
        Show.objects.filter(tvmaze_id=temp_id).update(tvmaze_id=new_id)
        Season.objects.filter(show_id=temp_id).update(show_id=new_id)
        Watchlist.objects.filter(show_id=temp_id).update(show_id=new_id)
        NextEpisode.objects.filter(show_id=temp_id).update(show_id=new_id)
        ShowUser.objects.filter(show_id=temp_id).update(show_id=new_id)


def remap_ids_to_trakt(apps, schema_editor):
    """Best-effort reverse, for `migrate mytvtime 0007`."""
    Show = apps.get_model('mytvtime', 'Show')
    Season = apps.get_model('mytvtime', 'Season')
    Watchlist = apps.get_model('mytvtime', 'Watchlist')
    NextEpisode = apps.get_model('mytvtime', 'NextEpisode')
    ShowUser = Show.users.through  # auto-created ManyToMany table

    current_ids = set(Show.objects.values_list('tvmaze_id', flat=True))
    if not current_ids:
        return
    reverse_mapping = {new_id: old_id for old_id, new_id in MAPPING.items()}
    unmapped = sorted(current_ids - set(reverse_mapping))
    if unmapped:
        raise RuntimeError(f'Cannot reverse the TVmaze id mapping for {unmapped}.')

    for new_id in sorted(reverse_mapping):
        temp_id = new_id + TEMP_OFFSET
        Show.objects.filter(tvmaze_id=new_id).update(tvmaze_id=temp_id)
        Season.objects.filter(show_id=new_id).update(show_id=temp_id)
        Watchlist.objects.filter(show_id=new_id).update(show_id=temp_id)
        NextEpisode.objects.filter(show_id=new_id).update(show_id=temp_id)
        ShowUser.objects.filter(show_id=new_id).update(show_id=temp_id)

    for new_id, old_id in reverse_mapping.items():
        temp_id = new_id + TEMP_OFFSET
        Show.objects.filter(tvmaze_id=temp_id).update(tvmaze_id=old_id)
        Season.objects.filter(show_id=temp_id).update(show_id=old_id)
        Watchlist.objects.filter(show_id=temp_id).update(show_id=old_id)
        NextEpisode.objects.filter(show_id=temp_id).update(show_id=old_id)
        ShowUser.objects.filter(show_id=temp_id).update(show_id=old_id)


class Migration(migrations.Migration):

    dependencies = [
        ('mytvtime', '0007_alter_nextepisode_timestamp_alter_show_timestamp_and_more'),
    ]

    operations = [
        # Show
        migrations.RenameField(
            model_name='show',
            old_name='trakt_id',
            new_name='tvmaze_id',
        ),
        migrations.RenameField(
            model_name='show',
            old_name='trakt_updated_at',
            new_name='tvmaze_updated_at',
        ),
        # NextEpisode
        migrations.RenameField(
            model_name='nextepisode',
            old_name='trakt_updated_at',
            new_name='tvmaze_updated_at',
        ),
        # Season / Episode are unused so far (no rows), renamed for consistency.
        migrations.RenameField(
            model_name='season',
            old_name='trakt_id',
            new_name='tvmaze_id',
        ),
        migrations.RenameField(
            model_name='episode',
            old_name='trakt_id',
            new_name='tvmaze_id',
        ),
        migrations.RunPython(remap_ids_to_tvmaze, remap_ids_to_trakt),
    ]
