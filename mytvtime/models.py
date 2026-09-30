from django.db import models
from django.contrib.auth.models import User


class Show(models.Model):
    # TVmaze's own show id (https://www.tvmaze.com/api). It has nothing to do
    # with Trakt's id sequence, which is why the old values were remapped by
    # migration 0008 when the data source was switched.
    tvmaze_id = models.PositiveIntegerField(primary_key=True)
    imdb_id = models.CharField(max_length=20, blank=True, null=True)
    tmdb_id = models.PositiveIntegerField(blank=True, null=True)
    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=255)
    year = models.PositiveIntegerField(blank=True, null=True)
    status = models.CharField(max_length=255, blank=True, null=True)
    overview = models.TextField(blank=True, null=True)
    # TVmaze's "updated" field for the show, as a datetime (it returns a Unix
    # timestamp).
    tvmaze_updated_at = models.DateTimeField(null=True, blank=True)
    poster_url = models.URLField(blank=True, null=True)
    backdrop_url = models.URLField(blank=True, null=True)
    users = models.ManyToManyField(User, related_name="shows")
    timestamp = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Title: {self.title}, Year: {self.year}, Status: {self.status}"


class Season(models.Model):
    tvmaze_id = models.PositiveIntegerField(primary_key=True)
    show = models.ForeignKey(Show, on_delete=models.CASCADE)
    season_number = models.PositiveIntegerField()
    first_aired = models.DateField(blank=True, null=True)
    overview = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.show.title} - Season {self.season_number}"


class Episode(models.Model):
    tvmaze_id = models.PositiveIntegerField(primary_key=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    episode_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    first_aired = models.DateField(blank=True, null=True)
    overview = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.season.show.title} - Season {self.season.season_number} - Episode {self.episode_number}"


class Watchlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    show = models.ForeignKey(Show, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'show')

    def __str__(self):
        return f"{self.user.username} - {self.show.title}"


class Watched(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'episode')

    def __str__(self):
        return f"{self.user.username} - {self.episode}"


class NextEpisode(models.Model):
    show = models.OneToOneField(Show, on_delete=models.CASCADE, related_name='next_episode')
    title = models.CharField(max_length=255, blank=True, null=True)
    season = models.IntegerField()
    number = models.IntegerField()
    air_date = models.DateTimeField(null=True, blank=True)
    # TVmaze does not expose an "updated" timestamp for episodes, so this stays
    # empty; NextEpisode.timestamp below records when the row was last written.
    tvmaze_updated_at = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.show.title} - S{self.season:02d}E{self.number:02d}"
