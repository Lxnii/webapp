import os, re, html, time, requests, json, logging
from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from datetime import datetime, timezone as dt_timezone
from django.utils.dateparse import parse_datetime
from configparser import ConfigParser

from .models import Show, Watchlist, NextEpisode

logger = logging.getLogger(__name__)

TVMAZE_API_URL = 'https://api.tvmaze.com'
tvmaze_headers = {
    'Accept': 'application/json'
    }
# TVmaze sends back no rate limit headers, but the documented limit is
# 20 requests / 10 seconds per IP, so keep a pause between calls when looping
# over many shows (used by the watchlist refresh paths).
TVMAZE_REQUEST_INTERVAL = 0.2

def get_api_key(api_name):
    config = ConfigParser()
    current_path = os.path.abspath(os.path.dirname(__file__))
    config_file = os.path.join(current_path, '..', 'config.ini')
    config.read(config_file)
    return config.get(api_name, 'api_key')

# TVmaze supplies the show data (search, details, air dates) and TMDB supplies
# the artwork (posters and backdrops). TMDB is optional: without a key the app
# still runs, just with TVmaze's poster and no backdrop.
try:
    tmdb_api_key = get_api_key('tmdb')
except Exception:
    tmdb_api_key = None

if not tmdb_api_key:
    logger.warning('No [tmdb] api_key found in config.ini, TMDB artwork is disabled')

TMDB_API_URL = 'https://api.themoviedb.org/3'
TMDB_IMAGE_URL = 'https://image.tmdb.org/t/p'
tmdb_headers = {
    'accept': 'application/json',
    'Authorization': tmdb_api_key
    } if tmdb_api_key else {}
# How many TMDB lookups to run at once when decorating search results.
TMDB_SEARCH_WORKERS = 8

# TVmaze uses its own status vocabulary; the rest of the app (and the frontend
# sorting in index.html) was written against Trakt's, so normalise to that.
TVMAZE_STATUS_MAP = {
    'running': 'returning series',
    'ended': 'ended',
    'cancelled': 'canceled',
    'to be determined': 'returning series',
    'in development': 'in development',
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

def strip_html_tags(value):
    # TVmaze returns summaries as HTML (e.g. "<p><b>Breaking Bad</b> follows...</p>").
    if not value:
        return value
    text = re.sub(r'<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()

def tvmaze_get(path, **params):
    """GET a TVmaze endpoint, retrying once if the rate limit (HTTP 429) is hit.

    TVmaze needs no API key and no OAuth. See https://www.tvmaze.com/api
    """
    url = f'{TVMAZE_API_URL}{path}'
    response = None
    for attempt in range(2):
        response = requests.get(url, headers=tvmaze_headers, params=params or None, timeout=10)
        if response.status_code != 429:
            return response
        try:
            delay = float(response.headers.get('Retry-After', ''))
        except (TypeError, ValueError):
            delay = 1.0
        logger.info(f'TVmaze rate limited on {path}, retrying in {delay}s')
        time.sleep(max(delay, TVMAZE_REQUEST_INTERVAL))
    return response

def unix_to_datetime(unix_timestamp):
    """TVmaze reports a show's "updated" field as a Unix timestamp."""
    if not unix_timestamp:
        return None
    return datetime.fromtimestamp(unix_timestamp, tz=dt_timezone.utc)

def map_tvmaze_status(status):
    if not status:
        return None
    return TVMAZE_STATUS_MAP.get(status.strip().lower(), status.strip().lower())

def search_shows_on_tvmaze(query):
    """Search TVmaze and return its raw list of {"score", "show"} dicts."""
    try:
        response = tvmaze_get('/search/shows', q=query)
        response.raise_for_status()  # Raises a HTTPError if the response status is 4xx, 5xx
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.info(f'Error occurred when searching shows on TVmaze API: {e}')
        return []

def normalize_tvmaze_show(tvmaze_show):
    """Map a TVmaze show object onto the fields this app displays/stores."""
    if not tvmaze_show:
        return None
    premiered = tvmaze_show.get('premiered') or ''
    year = int(premiered[:4]) if premiered[:4].isdigit() else None
    image = tvmaze_show.get('image') or {}
    externals = tvmaze_show.get('externals') or {}
    return {
        # TVmaze's own id. It is unrelated to Trakt's id sequence, which is why
        # migration 0008 remapped the stored ids when the source was switched.
        'tvmaze_id': tvmaze_show.get('id'),
        'title': tvmaze_show.get('name'),
        'year': year,
        'status': map_tvmaze_status(tvmaze_show.get('status')),
        'overview': strip_html_tags(tvmaze_show.get('summary')),
        # TVmaze has no TMDB id, and not every show carries an IMDb id.
        'imdb_id': externals.get('imdb'),
        'slug': (tvmaze_show.get('url') or '').rstrip('/').rsplit('/', 1)[-1] or None,
        # TVmaze only ships portrait posters, no backdrops.
        'poster_url': image.get('original') or image.get('medium'),
        'backdrop_url': None,
        'updated_at': unix_to_datetime(tvmaze_show.get('updated')),
    }

def normalize_tvmaze_episode(tvmaze_episode):
    """Map a TVmaze episode object onto the fields NextEpisode stores."""
    if not tvmaze_episode:
        return None
    first_aired = tvmaze_episode.get('airstamp')
    if not first_aired and tvmaze_episode.get('airdate'):
        # airstamp is missing for some episodes; fall back to the air date.
        first_aired = f"{tvmaze_episode['airdate']}T00:00:00+00:00"
    return {
        'title': tvmaze_episode.get('name'),
        'season': tvmaze_episode.get('season'),
        'number': tvmaze_episode.get('number'),
        'first_aired': first_aired,
        # TVmaze has no "updated" timestamp for episodes.
        'updated_at': None,
    }

def get_show_details_from_tvmaze(show_id):
    """Return normalised show details plus a 'next_episode' key (or None).

    The next episode comes from the embedded nextepisode, so a single request
    is enough - the TVmaze equivalent of Trakt's /shows/{id}/next_episode.
    """
    try:
        response = tvmaze_get(f'/shows/{show_id}', embed='nextepisode')
    except requests.exceptions.RequestException as e:
        logger.info(f'Error occurred when getting show details from TVmaze API: {e}')
        return None

    if response.status_code == 404:
        logger.info(f'Show {show_id} does not exist on TVmaze')
        return None
    response.raise_for_status()

    payload = response.json()
    show_details = normalize_tvmaze_show(payload)
    if show_details is None:
        return None
    embedded = payload.get('_embedded') or {}
    show_details['next_episode'] = normalize_tvmaze_episode(embedded.get('nextepisode'))
    return show_details

def tmdb_image_url(file_path, size):
    return f'{TMDB_IMAGE_URL}/{size}{file_path}' if file_path else None

def tmdb_get(path, **params):
    """GET a TMDB endpoint. Returns None when TMDB is unavailable or has no match."""
    if not tmdb_api_key:
        return None
    try:
        response = requests.get(f'{TMDB_API_URL}{path}', headers=tmdb_headers,
                                params=params or None, timeout=10)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.info(f'Error occurred when calling TMDB {path}: {e}')
        return None

def best_tmdb_image(images, preferred_languages=(None, 'en')):
    """Pick the nicest artwork: prefer textless (or English) artwork, then the
    best voted one. TVmaze has no backdrops, so this is the wallpaper source."""
    def rank(image):
        language = image.get('iso_639_1')
        try:
            language_rank = preferred_languages.index(language)
        except ValueError:
            language_rank = len(preferred_languages)
        return (language_rank, -(image.get('vote_count') or 0), -(image.get('vote_average') or 0))
    return min(images, key=rank) if images else None

def resolve_tmdb_id(imdb_id=None, title=None, year=None, known_id=None):
    """Return a TMDB tv id, preferring the one already stored for the show.

    TVmaze has no TMDB id, so new shows are matched through their IMDb id and,
    failing that, through a title/year search.
    """
    if known_id:
        return known_id
    if imdb_id:
        payload = tmdb_get(f'/find/{imdb_id}', external_source='imdb_id')
        results = (payload or {}).get('tv_results') or []
        if results:
            return results[0].get('id')
    if title:
        params = {'query': title, 'include_adult': 'false'}
        if year:
            params['first_air_date_year'] = year
        payload = tmdb_get('/search/tv', **params)
        results = (payload or {}).get('results') or []
        if results:
            return results[0].get('id')
    return None

def find_tmdb_artwork(imdb_id=None, title=None, year=None):
    """Resolve a TMDB show and its artwork with a single request.

    /find and /search/tv both return poster_path and backdrop_path, so
    decorating a search result costs one TMDB request instead of two.
    """
    result = None
    if imdb_id:
        payload = tmdb_get(f'/find/{imdb_id}', external_source='imdb_id')
        results = (payload or {}).get('tv_results') or []
        result = results[0] if results else None
    if result is None and title:
        params = {'query': title, 'include_adult': 'false'}
        if year:
            params['first_air_date_year'] = year
        payload = tmdb_get('/search/tv', **params)
        results = (payload or {}).get('results') or []
        result = results[0] if results else None
    if not result:
        return None
    return {
        'tmdb_id': result.get('id'),
        'poster_url': tmdb_image_url(result.get('poster_path'), 'w780'),
        'backdrop_url': tmdb_image_url(result.get('backdrop_path'), 'w780'),
    }

def get_show_artwork(tmdb_id=None, imdb_id=None, title=None, year=None):
    """TMDB artwork for a tracked show: full-size poster and best backdrop.

    Returns {'tmdb_id', 'poster_url', 'poster_w780_url', 'backdrop_url',
    'backdrop_w780_url'}, or None when TMDB cannot provide anything.
    """
    resolved_id = resolve_tmdb_id(imdb_id=imdb_id, title=title, year=year, known_id=tmdb_id)
    payload = tmdb_get(f'/tv/{resolved_id}', append_to_response='images') if resolved_id else None
    if not payload:
        # A stored id can go stale; resolve the show again before giving up.
        fresh_id = resolve_tmdb_id(imdb_id=imdb_id, title=title, year=year)
        if not fresh_id or fresh_id == resolved_id:
            return None
        resolved_id = fresh_id
        payload = tmdb_get(f'/tv/{fresh_id}', append_to_response='images')
        if not payload:
            return None
    images = payload.get('images') or {}
    poster = best_tmdb_image(images.get('posters'), preferred_languages=('en', None))
    backdrop = best_tmdb_image(images.get('backdrops'), preferred_languages=(None, 'en'))
    poster_path = payload.get('poster_path') or (poster or {}).get('file_path')
    backdrop_path = payload.get('backdrop_path') or (backdrop or {}).get('file_path')
    return {
        'tmdb_id': resolved_id,
        'poster_url': tmdb_image_url(poster_path, 'original'),
        'poster_w780_url': tmdb_image_url(poster_path, 'w780'),
        'backdrop_url': tmdb_image_url(backdrop_path, 'original'),
        'backdrop_w780_url': tmdb_image_url(backdrop_path, 'w780'),
    }

def apply_tmdb_artwork(show, artwork):
    """Override a normalised show dict with TMDB artwork, never with None."""
    if not artwork:
        return show
    for key in ('tmdb_id', 'poster_url', 'backdrop_url'):
        if artwork.get(key):
            show[key] = artwork[key]
    return show

def search_results(request):
    if request.method == 'POST':
        search_query = request.POST.get('search_query', '')

        if search_query:
            # Call the TVmaze API to search for shows
            raw_results = search_shows_on_tvmaze(search_query)

            search_results = []
            for raw_result in raw_results:
                show = normalize_tvmaze_show(raw_result.get('show'))
                if show is not None:
                    search_results.append(show)

            # TMDB is the app's artwork source, so upgrade the TVmaze posters to
            # TMDB ones (the TVmaze image stays as the fallback). The lookups are
            # independent of each other, so run them concurrently.
            if tmdb_api_key and search_results:
                with ThreadPoolExecutor(max_workers=TMDB_SEARCH_WORKERS) as executor:
                    artworks = list(executor.map(
                        lambda show: find_tmdb_artwork(show.get('imdb_id'), show.get('title'), show.get('year')),
                        search_results))
                for show, artwork in zip(search_results, artworks):
                    apply_tmdb_artwork(show, artwork)

            # Pass the search results to the frontend page for display
            context = {
                'search_query': search_query,
                'search_results': search_results,
            }
            return render(request, 'mytvtime/search_results.html', context)

    return render(request, 'mytvtime/index.html')

def save_next_episode(show, next_episode_details):
    """Create, update or delete the NextEpisode row of a show.

    TVmaze omits the embedded nextepisode (or leaves season/number empty) when
    a show has no upcoming episode, which is the equivalent of Trakt's 204.
    """
    if not next_episode_details or next_episode_details.get('season') is None \
            or next_episode_details.get('number') is None:
        NextEpisode.objects.filter(show=show).delete()
        return
    try:
        first_aired = next_episode_details.get('first_aired')
        updated_at = next_episode_details.get('updated_at')
        NextEpisode.objects.update_or_create(show=show,
            defaults={
                'title': next_episode_details.get('title'),
                'season': next_episode_details.get('season'),
                'number': next_episode_details.get('number'),
                'air_date': parse_datetime(first_aired) if first_aired else None,
                'tvmaze_updated_at': parse_datetime(updated_at) if updated_at else None})
    except Exception as e:
        logger.info(f'Error updating show_NextEpisode {show.slug}, id: {show.tvmaze_id}, error: {e}')

def update_show_info(show):
    # This function updates a Show object with the latest information from the TVmaze API
    show_details = get_show_details_from_tvmaze(show.tvmaze_id)
    if not show_details:
        logger.info(f'No TVmaze data for show {show.tvmaze_id}, keeping the stored values')
        return
    # Update the Show object with the new information
    show.title = show_details.get('title') or show.title
    show.year = show_details.get('year')
    if show_details.get('imdb_id'):
        # TVmaze does not always carry an IMDb id; never drop a known one.
        show.imdb_id = show_details.get('imdb_id')
    show.slug = show_details.get('slug') or show.slug
    show.status = show_details.get('status')
    show.overview = show_details.get('overview')
    show.tvmaze_updated_at = show_details.get('updated_at')
    # Artwork comes from TMDB; TVmaze only has a portrait poster as a fallback.
    artwork = get_show_artwork(show.tmdb_id,
        imdb_id=show_details.get('imdb_id') or show.imdb_id,
        title=show_details.get('title'),
        year=show_details.get('year'))
    if artwork:
        show.tmdb_id = artwork.get('tmdb_id') or show.tmdb_id
        show.poster_url = artwork.get('poster_url') or show.poster_url or show_details.get('poster_url')
        show.backdrop_url = artwork.get('backdrop_url') or show.backdrop_url
    else:
        # TMDB could not help: keep the stored artwork, or fall back to TVmaze.
        show.poster_url = show.poster_url or show_details.get('poster_url')
    show.save()
    save_next_episode(show, show_details.get('next_episode'))

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
            logger.info(f'Error updating show {show.tvmaze_id}: {e}')
        # Stay well below TVmaze's documented 20 requests / 10 seconds.
        time.sleep(TVMAZE_REQUEST_INTERVAL)
    logger.info(f'Finish updating the database data for all shows.')

@login_required
def update_user_watchlist_shows(request):
    user = request.user
    user_watchlist = Watchlist.objects.filter(user=user)
    for watchlist_item in user_watchlist:
        show = watchlist_item.show
        try:
            update_show_info(show)
        except Exception as e:
            logger.info(f'Error updating show {show.tvmaze_id}: {e}')
        time.sleep(TVMAZE_REQUEST_INTERVAL)
    return JsonResponse({"status": "success"})

@login_required
def add_show_to_watchlist(request, tvmaze_id):
    # Get the details of the selected show from the TVmaze API.
    selected_show_data = get_show_details_from_tvmaze(tvmaze_id)
    if not selected_show_data:
        messages.error(request, 'Could not load that show from TVmaze, please try again.')
        return redirect('mytvtime:index')

    # TVmaze sometimes holds duplicate entries for the same series, so prefer a
    # row that is already tracked under the same IMDb id over adding a copy.
    show = None
    imdb_id = selected_show_data.get('imdb_id')
    if imdb_id:
        show = Show.objects.filter(imdb_id=imdb_id).first()

    if show is None:
        # Artwork comes from TMDB; the TVmaze image is only the fallback.
        artwork = get_show_artwork(imdb_id=imdb_id,
                                   title=selected_show_data.get('title'),
                                   year=selected_show_data.get('year')) or {}
        defaults = {
            'imdb_id': imdb_id,
            'title': selected_show_data.get('title'),
            'slug': selected_show_data.get('slug'),
            'year': selected_show_data.get('year'),
            'status': selected_show_data.get('status'),
            'overview': selected_show_data.get('overview'),
            'tvmaze_updated_at': selected_show_data.get('updated_at'),
            'poster_url': artwork.get('poster_url') or selected_show_data.get('poster_url'),
            'backdrop_url': artwork.get('backdrop_url')}
        if artwork.get('tmdb_id'):
            defaults['tmdb_id'] = artwork['tmdb_id']
        show, created = Show.objects.update_or_create(
            tvmaze_id=selected_show_data.get('tvmaze_id'),
            defaults=defaults)
    else:
        update_show_info(show)

    show.users.add(request.user)
    show.save()
    save_next_episode(show, selected_show_data.get('next_episode'))
    # Create a new Watchlist entry for the current user and the selected show
    Watchlist.objects.get_or_create(user=request.user, show=show)
    return redirect('mytvtime:index')

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
            'tvmaze_id': show.tvmaze_id,
            'imdb': show.imdb_id,
            'tmdb': show.tmdb_id,
            'slug': show.slug,
            'season': next_episode.season if next_episode else None,
            'episode': next_episode.number if next_episode else None,
            'air_date': next_episode.air_date.isoformat() if next_episode and next_episode.air_date else None,
            'next_episode_tvmaze_updated_at': next_episode.tvmaze_updated_at.isoformat() if next_episode and next_episode.tvmaze_updated_at else None,
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
        tvmaze_id = data.get('tvmaze_id', None)
        if tvmaze_id is not None:
            # Get the Show object based on the TVmaze ID
            show = get_object_or_404(Show, tvmaze_id=tvmaze_id)
            
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
            return JsonResponse({"status": "error", "message": "TVmaze ID not provided"})
    else:
        return JsonResponse({"status": "error", "message": "Invalid request method"})
