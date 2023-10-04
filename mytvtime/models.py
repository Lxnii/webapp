from django.db import models
from django.contrib.auth.models import User
import os
import requests
from datetime import datetime, timedelta, timezone
from configparser import ConfigParser
# class UserProfile(models.Model):
#     user = models.OneToOneField(User, on_delete=models.CASCADE)
#     # Add other user-related fields (e.g., profile picture, biography)
    
#     def __str__(self):
#         return self.user.username

# def get_api_key(api_name):
#     config = ConfigParser()
#     config_file = os.path.join(os.path.dirname(__file__), '..', 'config.ini')
#     config.read(config_file)
#     return config.get(api_name, 'api_key')

# trakt_api_key = get_api_key('trakt')
# tmdb_api_key = get_api_key('tmdb')

# trakt_headers = {
#     'Content-Type': 'application/json',
#     'trakt-api-version': '2',
#     'trakt-api-key': trakt_api_key
#     }

class Show(models.Model):
    trakt_id = models.PositiveIntegerField(primary_key=True)
    imdb_id = models.CharField(max_length=20, blank=True, null=True)
    tmdb_id = models.PositiveIntegerField(blank=True, null=True)
    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=255)
    year = models.PositiveIntegerField(blank=True, null=True)
    status = models.CharField(max_length=255, blank=True, null=True)
    overview = models.TextField(blank=True, null=True)
    trakt_updated_at = models.DateTimeField(null=True, blank=True)
    poster_url = models.URLField(blank=True, null=True)
    backdrop_url = models.URLField(blank=True, null=True)
    users = models.ManyToManyField(User, related_name="shows")
    timestamp = models.DateTimeField(auto_now=True)
    # def refresh_from_api(self):
    #     trakt_api_url = f'https://api.trakt.tv/shows/{self.trakt_id}?extended=full'
    #     try:
    #         response = requests.get(trakt_api_url, headers=trakt_headers)
    #         response.raise_for_status()  # Raises a HTTPError if the response status is 4xx, 5xx
    #         show_details = response.json()

    #         # Update fields in the show instance
    #         self.trakt_id = show_details['ids']['trakt']
    #         self.imdb_id = show_details['ids']['imdb'],
    #         self.tmdb_id = show_details['ids']['tmdb'],
    #         self.slug = show_details['ids']['slug'],
    #         self.title = show_details['title']
    #         self.year = show_details['year']
    #         self.status = show_details['status']
    #         self.overview = show_details['overview']
    #         self.save()
    #     except requests.exceptions.RequestException as e:
    #         print(f"Error occurred when refreshing show details from Trakt API: {e}")

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
    trakt_updated_at = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now=True)

    
    # def refresh_from_api(self):
    #         trakt_api_url = f'https://api.trakt.tv/shows/{self.show.trakt_id}/next_episode?extended=full'
    #         try:
    #             response = requests.get(trakt_api_url, headers=trakt_headers)

    #             if response.status_code == 204:
    #                 # If there is no next episode, clear the fields
    #                 self.title = None
    #                 self.season = None
    #                 self.number = None
    #                 self.air_date = None
    #                 self.updated_at = None
    #             else:
    #                 response.raise_for_status()  # Raises a HTTPError if the response status is 4xx (other than 404), 5xx
    #                 next_episode_details = response.json()

    #                 self.title = next_episode_details['title']
    #                 self.season = next_episode_details['season']
    #                 self.number = next_episode_details['number']
    #                 self.air_date = datetime.strptime(next_episode_details['first_aired'], '%Y-%m-%dT%H:%M:%S.000Z')
    #                 self.updated_at = datetime.strptime(next_episode_details['updated_at'], '%Y-%m-%dT%H:%M:%S.000Z')
    #             self.save()
    #         except requests.exceptions.RequestException as e:
    #             print(f"Error occurred when refreshing next episode details from Trakt API: {e}")
    def __str__(self):
        return f"{self.show.title} - S{self.season:02d}E{self.number:02d}"
# class Review(models.Model):
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     show = models.ForeignKey(Show, on_delete=models.CASCADE)
#     episode = models.ForeignKey(Episode, on_delete=models.CASCADE, null=True, blank=True)
#     review_text = models.TextField()
#     timestamp = models.DateTimeField(auto_now_add=True)
