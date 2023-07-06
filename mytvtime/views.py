import os
import requests
from datetime import datetime, timedelta, timezone
from dateutil.parser import isoparse
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django.shortcuts import redirect
from configparser import ConfigParser
from .models import Show, Watchlist
# Create your views here.
# def index(request):
#     return render(request, "mytvtime/index.html")

def get_api_key(api_name):
    config = ConfigParser()
    config_file = os.path.join(os.path.dirname(__file__), '..', 'config.ini')
    config.read(config_file)
    return config.get(api_name, 'api_key')

trakt_api_key = get_api_key('trakt')
tmdb_api_key = get_api_key('tmdb')

trakt_headers = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': trakt_api_key
    }

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Registration successful.') 
            return redirect('mytvtime:index')
        messages.error(request, 'There was an error with your registration.')
    else:
        form = UserCreationForm()
    return render(request, 'mytvtime/register.html', {'form': form})

def login(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            django_login(request, user)
            return redirect('mytvtime:index')
    else:
        form = AuthenticationForm()
    return render(request, 'mytvtime/login.html', {'form': form})

def logout(request):
    django_logout(request)
    return redirect('mytvtime:index')

def index(request):
    watching_shows = []
    if request.user.is_authenticated:
        user = request.user.id
        user_watchlist = Watchlist.objects.filter(user=user)
        for watchlist_item in user_watchlist:
            show_id = watchlist_item.show.trakt_id  # Extract trakt_id from the show attribute of the Watchlist object
            show_details = get_show_details_from_trakt(show_id)
            if show_details is None:  # Add this check
                continue

            # Calculate the days and hours until the next episode
            next_episode = show_details.get('next_episode')
            next_episode_time = None
            days = None
            hours = None
            if next_episode is not None:  # And this check
                next_episode_time = isoparse(next_episode.get('first_aired')) # now includes timezone information
                now = datetime.now(timezone.utc)  # Corrected here
                time_delta = next_episode_time - now
                days = time_delta.days
                hours = time_delta.seconds // 3600

                # Adjustment for negative values of days and hours
                if days < 0 or hours < 0:
                    days = 0
                    hours = 0

            watching_show = {
                'title': show_details.get('title'),
                'season': next_episode.get('season') if next_episode else None,  # And check here
                'episode': next_episode.get('number') if next_episode else None,  # And here
                'days': days,
                'hours': hours,
                'status': show_details.get('status'),
            }

            watching_shows.append(watching_show)

    return render(request, 'mytvtime/index.html', {'watching_shows': watching_shows})

def search_shows_on_trakt(query):
    # Set Trakt API parameters
    trakt_api_url = 'https://api.trakt.tv/search/show?extended=full'
    params = {
        'query': query,
    }

    try:
        # Send a GET request to the Trakt API
        response = requests.get(trakt_api_url, headers=trakt_headers, params=params)
        response.raise_for_status()  # Raises a HTTPError if the response status is 4xx, 5xx

        # Parse the JSON data and return the search results if successful
        search_results = response.json()
        return search_results

    except requests.exceptions.RequestException as e:
        print(f"Error occurred when searching shows on Trakt API: {e}")
        return []

    
def search_results(request):
    if request.method == 'POST':
        search_query = request.POST.get('search_query', '')

        if search_query:
            # Call the Trakt API to search for shows
            search_results = search_shows_on_trakt(search_query)

            # Pass the search results to the frontend page for display
            context = {
                'search_query': search_query,
                'search_results': search_results,
            }

            return render(request, 'mytvtime/search_results.html', context)

    return render(request, 'mytvtime/index.html')

# def get_show_details_from_trakt(show_id):
#     trakt_api_url = f'https://api.trakt.tv/shows/{show_id}?extended=full'
#     try:
#         response = requests.get(trakt_api_url, headers=trakt_headers)
#         response.raise_for_status()  # Raises a HTTPError if the response status is 4xx, 5xx
#         show_details = response.json()
#         return show_details
#     except requests.exceptions.RequestException as e:
#         print(f"Error occurred when getting show details from Trakt API: {e}")
#         return None

def get_show_details_from_trakt(show_id):

    # URLs for Trakt API: Show Summary, Next Episode Info
    trakt_api_url = f'https://api.trakt.tv/shows/{show_id}?extended=full'
    trakt_api_next_episode_url = f'https://api.trakt.tv/shows/{show_id}/next_episode?extended=full'
    
    # Send a GET request to the Trakt API for show details
    response = requests.get(trakt_api_url, headers=trakt_headers)
    response.raise_for_status()
    show_details = response.json()

    # Try to get the next episode details
    response = requests.get(trakt_api_next_episode_url, headers=trakt_headers)
    
    if response.status_code == 200:  # If the next episode exists
        next_episode_details = response.json()

        show_details.update({
            'next_episode': {
                'season': next_episode_details.get('season'),
                'number': next_episode_details.get('number'),
                'first_aired': next_episode_details.get('first_aired'),
            }
        })
    elif response.status_code == 204:  # If the next episode does not exist
        show_details.update({
            'next_episode': None
        })

    return show_details

@login_required
def add_to_watchlist(request, trakt_id):
    # Search and get detail data from trakt API for selected show.
    selected_show_data = get_show_details_from_trakt(trakt_id)
    # Get or create the Show object based on the Trakt ID
    show, created = Show.objects.get_or_create(trakt_id=selected_show_data['ids']['trakt'],
                                               imdb_id = selected_show_data['ids']['imdb'],
                                               tmdb_id = selected_show_data['ids']['tmdb'],
                                               title = selected_show_data['title'],
                                               slug = selected_show_data['ids']['slug'],
                                               year = selected_show_data['year'],
                                               status = selected_show_data['status'])
    
    # Create a new Watchlist entry for the current user and the selected show
    Watchlist.objects.get_or_create(user=request.user, show=show)
    
    # Redirect the user back to the home page
    return redirect('mytvtime:index')


