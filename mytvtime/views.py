import os, sys, requests, json, logging

from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from configparser import ConfigParser
from .models import Show, Watchlist, NextEpisode

logger = logging.getLogger(__name__)

def get_api_key(api_name):
    config = ConfigParser()
    current_path = os.path.abspath(os.path.dirname(__file__))
    config_file = os.path.join(current_path, '..', 'config.ini')
    config.read(config_file)
    return config.get(api_name, 'api_key')

trakt_api_key = get_api_key('trakt')
tmdb_api_key = get_api_key('tmdb')

trakt_headers = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2',
    'trakt-api-key': trakt_api_key
    }
tmdb_headers = {
    'accept': 'application/json',
    'Authorization': tmdb_api_key
    }

def index(request):
    return render(request, 'mytvtime/index.html')

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
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                django_login(request, user)
                return redirect('mytvtime:index')
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    return render(request, 'mytvtime/login.html', {'form': form})


def logout(request):
    django_logout(request)
    return redirect('mytvtime:index')

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

            # Add a poster_url from TMDB to each search result
            for result in search_results:
                tmdb_id = result['show']['ids']['tmdb']
                images_url = get_show_images_from_tmdb(tmdb_id)
                if images_url is not None:
                    result['show']['poster_url'] = images_url['poster_w780_url']
                else:
                    result['show']['poster_url'] = None  # or set a default poster URL

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
                'title': next_episode_details.get('title'),
                'season': next_episode_details.get('season'),
                'number': next_episode_details.get('number'),
                'first_aired': next_episode_details.get('first_aired'),
                'updated_at': next_episode_details.get('updated_at')
            }
        })
    elif response.status_code == 204:  # If the next episode does not exist
        show_details.update({
            'next_episode': None
        })

    return show_details

def get_show_images_from_tmdb(tmdb_id):
    tmdb_api_url = f'https://api.themoviedb.org/3/tv/{tmdb_id}/images'
    try:
        response = requests.get(tmdb_api_url, headers=tmdb_headers)
        response.raise_for_status()
        show_details = response.json()
        poster_path = show_details.get('posters',[])
        poster_url = f'https://image.tmdb.org/t/p/original{poster_path[0]["file_path"]}' if poster_path else None
        poster_w780_url = f'https://image.tmdb.org/t/p/w780{poster_path[0]["file_path"]}' if poster_path else None
        backdrops_path = show_details.get('backdrops', [])
        backdrop_url = f'https://image.tmdb.org/t/p/original{backdrops_path[0]["file_path"]}' if backdrops_path else None

        return {'poster_url': poster_url, 
                'poster_w780_url': poster_w780_url, 
                'backdrop_url': backdrop_url}
    except requests.exceptions.RequestException as e:
        print(f"Error occurred when getting show images from TMDB API: {e}")
        return None

def update_show_info(show):
    # This function updates a Show object with the latest information from the Trakt API
    show_details = get_show_details_from_trakt(show.trakt_id)
    # TMDb_id = show_details.get('ids', {}).get('tmdb')
    images_url = get_show_images_from_tmdb(show.tmdb_id)
    if images_url == None:
        images_url ={'poster_url': None, 'poster_w780_url': None, 'backdrop_url': None}
    # Update the Show object with the new information
    show.title = show_details.get('title')
    show.year = show_details.get('year')
    show.imdb_id = show_details.get('ids', {}).get('imdb')
    show.tmdb_id = show_details.get('ids', {}).get('tmdb')
    show.title = show_details.get('title')
    show.slug = show_details.get('ids', {}).get('slug')
    show.status = show_details.get('status')
    show.overview = show_details.get('overview')
    show.trakt_updated_at = show_details.get('updated_at')
    show.poster_url = images_url.get('poster_url')
    show.backdrop_url = images_url.get('backdrop_url')
    # Get the next episode details
    next_episode_details = show_details.get('next_episode')
    if next_episode_details:
        try:
            next_episode, created = NextEpisode.objects.update_or_create(show=show,
                defaults={
                    'title': next_episode_details.get('title'),
                    'season': next_episode_details.get('season'),
                    'number': next_episode_details.get('number'),
                    'air_date': parse_datetime(next_episode_details.get('first_aired')),
                    'trakt_updated_at': parse_datetime(next_episode_details.get('updated_at'))})
            next_episode.save()
        except Exception as e:
            logger.info(f'Error updating show_NextEpisode {show.slug}, id: {show.trakt_id}, error: {e}')
    else:
    # If no next episode details available, delete the existing NextEpisode object from the database
        NextEpisode.objects.filter(show=show).delete()
    show.save()

def update_all_database_shows(request):
    # This view updates all shows in the database
    for show in Show.objects.all():
        update_show_info(show)
    # Return a success response
    return JsonResponse({"status": "success"})

def auto_update_all_database_shows():
    logger.info('Starting to update all database shows...')
    shows = Show.objects.all()
    for show in shows:
        try:
            update_show_info(show)
        except Exception as e:
            logger.info(f'Error updating show {show.trakt_id}: {e}')
    logger.info(f'Finish updating the database data for all shows.')

# def update_database_view(request):
#     logging.debug("Received request for update_database_view")
#     auto_update_all_database_shows()
#     return JsonResponse({'status': 'success'})

@login_required
def update_user_watchlist_shows(request):
    user = request.user
    user_watchlist = Watchlist.objects.filter(user=user)
    for watchlist_item in user_watchlist:
        show = watchlist_item.show
        update_show_info(show)
    return JsonResponse({"status": "success"})

@login_required
def add_show_to_watchlist(request, trakt_id):
    # Search and get detail data from trakt API for selected show.
    selected_show_data = get_show_details_from_trakt(trakt_id)
    tmdb_id = selected_show_data['ids']['tmdb']    
    images_url = get_show_images_from_tmdb(tmdb_id)
    if images_url == None:
        images_url ={'poster_url': None, 'poster_w780_url': None, 'backdrop_url': None}
    # Get or create the Show object based on the Trakt ID
    show, created = Show.objects.update_or_create(trakt_id=selected_show_data.get('ids').get('trakt'),
        defaults={
            'imdb_id': selected_show_data.get('ids', {}).get('imdb'),
            'tmdb_id': selected_show_data.get('ids', {}).get('tmdb'),
            'title': selected_show_data.get('title'),
            'slug': selected_show_data.get('ids', {}).get('slug'),
            'year': selected_show_data.get('year'),
            'status': selected_show_data.get('status'),
            'overview': selected_show_data.get('overview'),
            'trakt_updated_at': selected_show_data.get('updated_at'),
            'poster_url': images_url.get('poster_url'),
            'backdrop_url': images_url.get('backdrop_url')})
    show.users.add(request.user)
    show.save()
    next_episode_details = selected_show_data.get('next_episode')

    if next_episode_details:
        try:
            next_episode, created = NextEpisode.objects.update_or_create(show=show,
                defaults={
                    'title': next_episode_details.get('title'),
                    'season': next_episode_details.get('season'),
                    'number': next_episode_details.get('number'),
                    'air_date': parse_datetime(next_episode_details.get('first_aired')),
                    'trakt_updated_at': parse_datetime(next_episode_details.get('updated_at'))})
            next_episode.save()
        except Exception as e:
            logger.info(f'Error adding show_NextEpisode to Watchlist {show.slug}, id: {show.trakt_id}, error: {e}')
    # Create a new Watchlist entry for the current user and the selected show
    Watchlist.objects.get_or_create(user=request.user, show=show)
    return redirect('mytvtime:index')

# @login_required
# def get_watching_shows(request):
#     if request.user.is_authenticated:
#         user_id = request.user.id
#         watching_shows = []
#         user_watchlist = Watchlist.objects.filter(user=user_id)
#         for watchlist_item in user_watchlist:
#             show = watchlist_item.show

#             # Get the next episode if it exists
#             next_episode = show.next_episode.first() if show.next_episode.exists() else None

#             # If the next episode has aired, update the show and next episode details
#             if next_episode and next_episode.air_date and next_episode.air_date < timezone.now():
#                 show_details = get_show_details_from_trakt(show.trakt_id)
#                 new_show_datailes = show_details
#                 logger.info('找到过时的下一集时间show,并从trakt更新')
#                 # Update the next episode info in the database
#                 next_episode_details = show_details.get('next_episode')
#                 if next_episode_details:
#                     next_episode.title = next_episode_details.get('title')
#                     next_episode.season = next_episode_details.get('season')
#                     next_episode.number = next_episode_details.get('number')
#                     next_episode.air_date = parse_datetime(next_episode_details.get('first_aired'))
#                     next_episode.trakt_updated_at = parse_datetime(next_episode_details.get('updated_at'))
#                     # test_show_next_episode_trakt_updated_at = parse_datetime(next_episode_details.get('updated_at'))
#                     next_episode.save()
#                 # Get the updated next episode
#                 next_episode = show.next_episode.first() if show.next_episode.exists() else None

#             # Initialize watching_show dictionary
#             watching_show = {
#                 'title': show.title,
#                 'trakt': show.trakt_id,
#                 'imdb': show.imdb_id,
#                 'tmdb': show.tmdb_id,
#                 'slug': show.slug,
#                 'season': next_episode.season if next_episode else None,
#                 'episode': next_episode.number if next_episode else None,
#                 'days': None,
#                 'hours': None,
#                 'minutes': None,
#                 'status': 'Returning' if show.status == 'returning series' else show.status.capitalize(),
#                 'poster_url': show.poster_url,
#                 'backdrop_url': show.backdrop_url
#             }

#             # Calculate the days and hours until the next episode
#             if next_episode and next_episode.air_date is not None:
#                 next_episode_time = next_episode.air_date
#                 now = timezone.now()  # get current time with timezone
#                 time_delta = next_episode_time - now
#                 days = time_delta.days
#                 hours = time_delta.seconds // 3600
#                 minutes = (time_delta.seconds // 60) % 60

#                 # Update 'days' and 'hours' fields
#                 watching_show['days'] = days
#                 watching_show['hours'] = hours
#                 watching_show['minutes'] = minutes
#                 watching_show['trakt_next_episode_update_date'] = next_episode.trakt_updated_at
#             watching_shows.append(watching_show)

#         # Sort user's watchlist to front end.
#         def sort_shows(show):
#             """
#             Custom sorting function for shows.
#             Returning series are put at the front, ended shows are put at the end,
#             and other shows are sorted by their next episode air time.
#             """
#             if show['status'].lower() == 'returning' and show['days'] is None:
#                 return (1e10, show['title'])
#             elif show['status'].lower() == 'ended':
#                 return (2 * 1e10, show['title'])
#             elif show['days'] is not None:
#                 return ((show['days'] * 24 * 60 + show['hours'] * 60 + show['minutes']), show['title'])
#             else:
#                 return (2 * 1e10, show['title'])  # Other shows without a next episode are sorted to the end

#         watching_shows = sorted(watching_shows, key=sort_shows)

#         return JsonResponse({'watching_shows': watching_shows})

#     else:
#         # If the user is not authenticated, return a JSON object with an "unauthenticated" field.
#         return JsonResponse({'unauthenticated': True}, safe=False)

@login_required
def get_watching_shows(request):
    # Check if the user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'unauthenticated': True}, safe=False)

    current_user = request.user
    user_watchlist = Watchlist.objects.filter(user=current_user)

    # Prepare the data to return
    shows_data = []
    for watchlist_item in user_watchlist:
        show = watchlist_item.show
        try:
            next_episode = show.next_episode
        except NextEpisode.DoesNotExist:
            next_episode = None
        # If the next episode has aired, update the show and next episode details
        if next_episode and next_episode.air_date and next_episode.air_date < timezone.now():
            update_show_info(show)  # Update the show data
            show.refresh_from_db()
            next_episode = show.next_episode

        # Prepare the data for a single show
        watching_show = {
            'title': show.title,
            'trakt': show.trakt_id,
            'imdb': show.imdb_id,
            'tmdb': show.tmdb_id,
            'slug': show.slug,
            'season': next_episode.season if next_episode else None,
            'episode': next_episode.number if next_episode else None,
            'air_date': next_episode.air_date.isoformat() if next_episode and next_episode.air_date else None,
            'next_episode_trakt_updated_at': next_episode.trakt_updated_at.isoformat() if next_episode and next_episode.trakt_updated_at else None,
            'show_update_timestamp': show.timestamp.isoformat(),
            'next_episode_update_timestamp': next_episode.timestamp.isoformat() if next_episode and next_episode.timestamp else None,
            'status': 'Returning' if show.status == 'returning series' else show.status.capitalize(),
            'poster_url': show.poster_url,
            'backdrop_url': show.backdrop_url
        }

        shows_data.append(watching_show)

    return JsonResponse({'watching_shows': shows_data})


@login_required
def remove_show_from_watchlist(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        trakt_id = data.get('trakt_id', None)
        if trakt_id is not None:
            # Get the Show object based on the Trakt ID
            show = get_object_or_404(Show, trakt_id=trakt_id)
            
            # Remove the user from the Show's users list
            show.users.remove(request.user)
            
            # Also remove the show from the user's Watchlist
            Watchlist.objects.filter(user=request.user, show=show).delete()

            # Check if the show is still on any user's Watchlist
            if not show.users.exists():
                # If the show is not on any user's Watchlist, delete it from the database
                show.delete()
            
            return JsonResponse({"status": "success"})
        else:
            return JsonResponse({"status": "error", "message": "Trakt ID not provided"})
    else:
        return JsonResponse({"status": "error", "message": "Invalid request method"})
