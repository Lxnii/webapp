from django.db import models
from django.contrib.auth.models import User

# class UserProfile(models.Model):
#     user = models.OneToOneField(User, on_delete=models.CASCADE)
#     # Add other user-related fields (e.g., profile picture, biography)
    
#     def __str__(self):
#         return self.user.username

class Show(models.Model):
    trakt_id = models.PositiveIntegerField(primary_key=True)
    imdb_id = models.CharField(max_length=20, blank=True, null=True)
    tmdb_id = models.PositiveIntegerField(blank=True, null=True)
    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=255)
    year = models.PositiveIntegerField()
    status = models.CharField(max_length=255)
    overview = models.TextField(blank=True, null=True)
    poster_url = models.URLField(blank=True, null=True)
    backdrop_url = models.URLField(blank=True, null=True)
    
    def __str__(self):
        return f"Title: {self.title}, Year: {self.year}, Status: {self.status}"
    
class Season(models.Model):
    trakt_id = models.PositiveIntegerField(primary_key=True)
    show = models.ForeignKey(Show, on_delete=models.CASCADE)
    season_number = models.PositiveIntegerField()
    first_aired = models.DateField(blank=True, null=True)
    overview = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.show.title} - Season {self.season_number}"
    
class Episode(models.Model):
    trakt_id = models.PositiveIntegerField(primary_key=True)
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
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'show')

    def __str__(self):
        return f"{self.user.username} - {self.show.title}"

class Watched(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'episode')

    def __str__(self):
        return f"{self.user.username} - {self.episode}"

# class Review(models.Model):
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     show = models.ForeignKey(Show, on_delete=models.CASCADE)
#     episode = models.ForeignKey(Episode, on_delete=models.CASCADE, null=True, blank=True)
#     review_text = models.TextField()
#     timestamp = models.DateTimeField(auto_now_add=True)
