import json
from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from . import views
from .models import NextEpisode, Show, Watchlist

# Trimmed-down copy of a real TVmaze /search/shows response (Severance, show 44933).
TVMAZE_SEARCH_PAYLOAD = [
    {
        "score": 1.2,
        "show": {
            "id": 44933,
            "url": "https://www.tvmaze.com/shows/44933/severance",
            "name": "Severance",
            "status": "Running",
            "premiered": "2022-02-18",
            "externals": {"tvrage": None, "thetvdb": 371980, "imdb": "tt11280740"},
            "image": {
                "medium": "https://static.tvmaze.com/uploads/images/medium_portrait/1/severance.jpg",
                "original": "https://static.tvmaze.com/uploads/images/original_untouched/1/severance.jpg",
            },
            "summary": "<p><b>Severance</b> follows Mark &amp; his colleagues.</p>",
            "updated": 1769198028,
        },
    },
    {
        "score": 0.4,
        "show": {
            "id": 4242,
            "url": "https://www.tvmaze.com/shows/4242/no-poster-show",
            "name": "No Poster Show",
            "status": "To Be Determined",
            "premiered": None,
            "externals": {"tvrage": 1, "thetvdb": None, "imdb": None},
            "image": None,
            "summary": None,
            "updated": 1700000000,
        },
    },
]

# /shows/44933?embed=nextepisode
TVMAZE_SHOW_PAYLOAD = {
    "id": 44933,
    "url": "https://www.tvmaze.com/shows/44933/severance",
    "name": "Severance",
    "status": "Running",
    "premiered": "2022-02-18",
    "externals": {"tvrage": None, "thetvdb": 371980, "imdb": "tt11280740"},
    "image": {
        "medium": "https://static.tvmaze.com/uploads/images/medium_portrait/1/severance.jpg",
        "original": "https://static.tvmaze.com/uploads/images/original_untouched/1/severance.jpg",
    },
    "summary": "<p>Mark leads a team at Lumon.</p>",
    "updated": 1769198028,
    "_embedded": {
        "nextepisode": {
            "id": 900001,
            "name": "Cold Harbor",
            "season": 3,
            "number": 1,
            "airdate": "2026-10-15",
            "airstamp": "2026-10-15T01:00:00+00:00",
            "summary": None,
        }
    },
}

# /tv/95396?append_to_response=images
TMDB_SHOW_PAYLOAD = {
    "id": 95396,
    "name": "Severance",
    "poster_path": "/default-poster.jpg",
    "backdrop_path": "/default-backdrop.jpg",
    "images": {
        "posters": [
            {"file_path": "/fr-poster.jpg", "iso_639_1": "fr", "vote_count": 9, "vote_average": 9.0},
            {"file_path": "/en-poster.jpg", "iso_639_1": "en", "vote_count": 3, "vote_average": 5.0},
        ],
        "backdrops": [
            {"file_path": "/textless-backdrop.jpg", "iso_639_1": None, "vote_count": 4, "vote_average": 6.0},
            {"file_path": "/de-backdrop.jpg", "iso_639_1": "de", "vote_count": 50, "vote_average": 9.0},
        ],
    },
}

TMDB_ARTWORK = {
    "tmdb_id": 95396,
    "poster_url": "https://image.tmdb.org/t/p/original/default-poster.jpg",
    "poster_w780_url": "https://image.tmdb.org/t/p/w780/default-poster.jpg",
    "backdrop_url": "https://image.tmdb.org/t/p/original/default-backdrop.jpg",
    "backdrop_w780_url": "https://image.tmdb.org/t/p/w780/default-backdrop.jpg",
}


def fake_response(payload, status_code=200):
    response = mock.Mock(status_code=status_code)
    response.json.return_value = payload
    return response


class NormalizeTvmazeShowTests(TestCase):
    def test_maps_tvmaze_fields(self):
        show = views.normalize_tvmaze_show(TVMAZE_SEARCH_PAYLOAD[0]["show"])

        self.assertEqual(show["tvmaze_id"], 44933)
        self.assertEqual(show["title"], "Severance")
        self.assertEqual(show["year"], 2022)
        self.assertEqual(show["imdb_id"], "tt11280740")
        self.assertEqual(show["slug"], "severance")
        self.assertEqual(show["poster_url"], TVMAZE_SEARCH_PAYLOAD[0]["show"]["image"]["original"])
        self.assertEqual(show["overview"], "Severance follows Mark & his colleagues.")
        self.assertEqual(
            show["updated_at"], datetime.fromtimestamp(1769198028, tz=dt_timezone.utc)
        )

    def test_missing_image_year_and_summary_are_tolerated(self):
        show = views.normalize_tvmaze_show(TVMAZE_SEARCH_PAYLOAD[1]["show"])

        self.assertIsNone(show["poster_url"])
        self.assertIsNone(show["year"])
        self.assertIsNone(show["imdb_id"])
        self.assertIsNone(show["overview"])

    def test_empty_show_returns_none(self):
        self.assertIsNone(views.normalize_tvmaze_show(None))
        self.assertIsNone(views.normalize_tvmaze_show({}))

    def test_strip_html_tags(self):
        self.assertEqual(views.strip_html_tags("<p>Hello <b>world</b></p>"), "Hello world")
        self.assertEqual(views.strip_html_tags(None), None)


class MapTvmazeStatusTests(TestCase):
    def test_tvmaze_statuses_are_mapped_to_the_apps_vocabulary(self):
        self.assertEqual(views.map_tvmaze_status("Running"), "returning series")
        self.assertEqual(views.map_tvmaze_status("Ended"), "ended")
        self.assertEqual(views.map_tvmaze_status("Cancelled"), "canceled")
        self.assertEqual(views.map_tvmaze_status("To Be Determined"), "returning series")
        self.assertEqual(views.map_tvmaze_status(None), None)


class NormalizeTvmazeEpisodeTests(TestCase):
    def test_uses_airstamp_for_the_air_datetime(self):
        episode = views.normalize_tvmaze_episode(TVMAZE_SHOW_PAYLOAD["_embedded"]["nextepisode"])

        self.assertEqual(episode["title"], "Cold Harbor")
        self.assertEqual(episode["season"], 3)
        self.assertEqual(episode["number"], 1)
        self.assertEqual(episode["first_aired"], "2026-10-15T01:00:00+00:00")
        self.assertIsNone(episode["updated_at"])

    def test_falls_back_to_airdate_when_airstamp_is_missing(self):
        episode = views.normalize_tvmaze_episode(
            {"name": "Some episode", "season": 1, "number": 2, "airdate": "2026-10-15", "airstamp": None}
        )

        self.assertEqual(episode["first_aired"], "2026-10-15T00:00:00+00:00")

    def test_empty_episode_returns_none(self):
        self.assertIsNone(views.normalize_tvmaze_episode(None))
        self.assertIsNone(views.normalize_tvmaze_episode({}))


class TvmazeRequestTests(TestCase):
    @mock.patch("mytvtime.views.requests.get")
    def test_search_hits_the_tvmaze_search_endpoint(self, mock_get):
        mock_get.return_value = fake_response(TVMAZE_SEARCH_PAYLOAD)

        results = views.search_shows_on_tvmaze("severance")

        self.assertEqual(results, TVMAZE_SEARCH_PAYLOAD)
        self.assertEqual(mock_get.call_args.args[0], "https://api.tvmaze.com/search/shows")
        self.assertEqual(mock_get.call_args.kwargs["params"], {"q": "severance"})

    @mock.patch("mytvtime.views.requests.get")
    def test_show_details_embed_the_next_episode(self, mock_get):
        mock_get.return_value = fake_response(TVMAZE_SHOW_PAYLOAD)

        details = views.get_show_details_from_tvmaze(44933)

        self.assertEqual(details["title"], "Severance")
        self.assertEqual(details["status"], "returning series")
        self.assertEqual(details["next_episode"]["title"], "Cold Harbor")
        self.assertEqual(mock_get.call_args.args[0], "https://api.tvmaze.com/shows/44933")
        self.assertEqual(mock_get.call_args.kwargs["params"], {"embed": "nextepisode"})

    @mock.patch("mytvtime.views.requests.get")
    def test_show_without_a_next_episode_has_none(self, mock_get):
        mock_get.return_value = fake_response(dict(TVMAZE_SHOW_PAYLOAD, _embedded={}))

        self.assertIsNone(views.get_show_details_from_tvmaze(44933)["next_episode"])

    @mock.patch("mytvtime.views.requests.get")
    def test_unknown_show_returns_none(self, mock_get):
        mock_get.return_value = fake_response({}, status_code=404)

        self.assertIsNone(views.get_show_details_from_tvmaze(999999))

    @mock.patch("mytvtime.views.requests.get")
    def test_rate_limited_request_is_retried(self, mock_get):
        mock_get.side_effect = [
            fake_response({}, status_code=429),
            fake_response(TVMAZE_SHOW_PAYLOAD),
        ]

        details = views.get_show_details_from_tvmaze(44933)

        self.assertEqual(details["title"], "Severance")
        self.assertEqual(mock_get.call_count, 2)

    @mock.patch("mytvtime.views.requests.get")
    def test_search_failure_returns_no_results(self, mock_get):
        mock_get.side_effect = views.requests.exceptions.ConnectionError("boom")

        self.assertEqual(views.search_shows_on_tvmaze("severance"), [])


class TmdbHelperTests(TestCase):
    def test_image_url_builder(self):
        self.assertEqual(
            views.tmdb_image_url("/poster.jpg", "w780"),
            "https://image.tmdb.org/t/p/w780/poster.jpg",
        )
        self.assertIsNone(views.tmdb_image_url(None, "w780"))

    def test_best_image_prefers_textless_then_most_voted(self):
        backdrops = TMDB_SHOW_PAYLOAD["images"]["backdrops"]
        posters = TMDB_SHOW_PAYLOAD["images"]["posters"]

        self.assertEqual(
            views.best_tmdb_image(backdrops, preferred_languages=(None, "en"))["file_path"],
            "/textless-backdrop.jpg",
        )
        self.assertEqual(
            views.best_tmdb_image(posters, preferred_languages=("en", None))["file_path"],
            "/en-poster.jpg",
        )
        self.assertIsNone(views.best_tmdb_image([], preferred_languages=(None,)))

    @mock.patch("mytvtime.views.tmdb_get")
    def test_find_artwork_uses_imdb_when_available(self, mock_tmdb_get):
        mock_tmdb_get.return_value = {
            "tv_results": [{"id": 95396, "poster_path": "/p.jpg", "backdrop_path": "/b.jpg"}]
        }

        artwork = views.find_tmdb_artwork(imdb_id="tt11280740", title="Severance", year=2022)

        self.assertEqual(artwork["tmdb_id"], 95396)
        self.assertEqual(artwork["poster_url"], "https://image.tmdb.org/t/p/w780/p.jpg")
        self.assertEqual(artwork["backdrop_url"], "https://image.tmdb.org/t/p/w780/b.jpg")
        self.assertEqual(mock_tmdb_get.call_args.args[0], "/find/tt11280740")
        self.assertEqual(mock_tmdb_get.call_args.kwargs["external_source"], "imdb_id")

    @mock.patch("mytvtime.views.tmdb_get")
    def test_find_artwork_falls_back_to_a_title_search(self, mock_tmdb_get):
        mock_tmdb_get.side_effect = [
            {"tv_results": []},
            {"results": [{"id": 79529, "poster_path": "/ling.jpg", "backdrop_path": None}]},
        ]

        artwork = views.find_tmdb_artwork(imdb_id="tt10827146", title="Ling Cage", year=2020)

        self.assertEqual(artwork["tmdb_id"], 79529)
        self.assertEqual(mock_tmdb_get.call_args.args[0], "/search/tv")
        self.assertEqual(mock_tmdb_get.call_args.kwargs["query"], "Ling Cage")
        self.assertEqual(mock_tmdb_get.call_args.kwargs["first_air_date_year"], 2020)

    @mock.patch("mytvtime.views.tmdb_get")
    def test_find_artwork_returns_none_when_tmdb_has_no_match(self, mock_tmdb_get):
        mock_tmdb_get.return_value = {"tv_results": [], "results": []}

        self.assertIsNone(views.find_tmdb_artwork(imdb_id="tt0", title="Nothing", year=None))

    @mock.patch("mytvtime.views.tmdb_get")
    def test_show_artwork_uses_the_curated_poster_and_backdrop(self, mock_tmdb_get):
        mock_tmdb_get.return_value = TMDB_SHOW_PAYLOAD

        artwork = views.get_show_artwork(tmdb_id=95396, imdb_id="tt11280740")

        self.assertEqual(artwork["tmdb_id"], 95396)
        self.assertEqual(artwork["poster_url"], "https://image.tmdb.org/t/p/original/default-poster.jpg")
        self.assertEqual(artwork["backdrop_url"], "https://image.tmdb.org/t/p/original/default-backdrop.jpg")
        self.assertEqual(artwork["backdrop_w780_url"], "https://image.tmdb.org/t/p/w780/default-backdrop.jpg")
        self.assertEqual(mock_tmdb_get.call_args.args[0], "/tv/95396")
        self.assertEqual(mock_tmdb_get.call_args.kwargs["append_to_response"], "images")

    @mock.patch("mytvtime.views.tmdb_get")
    def test_show_artwork_resolves_a_stale_stored_id_via_imdb(self, mock_tmdb_get):
        mock_tmdb_get.side_effect = [
            None,  # /tv/<stale id> no longer exists
            {"tv_results": [{"id": 95396}]},  # /find by imdb
            TMDB_SHOW_PAYLOAD,  # /tv/95396
        ]

        artwork = views.get_show_artwork(tmdb_id=1, imdb_id="tt11280740", title="Severance")

        self.assertEqual(artwork["tmdb_id"], 95396)
        self.assertEqual(mock_tmdb_get.call_count, 3)

    @mock.patch("mytvtime.views.tmdb_get")
    def test_show_artwork_returns_none_when_tmdb_cannot_help(self, mock_tmdb_get):
        mock_tmdb_get.return_value = None

        self.assertIsNone(views.get_show_artwork(tmdb_id=95396, imdb_id="tt11280740"))

    @mock.patch("mytvtime.views.requests.get")
    def test_tmdb_get_is_skipped_without_an_api_key(self, mock_get):
        with mock.patch.object(views, "tmdb_api_key", None):
            self.assertIsNone(views.tmdb_get("/tv/95396"))
            self.assertIsNone(views.get_show_artwork(tmdb_id=95396))

        mock_get.assert_not_called()


class SearchResultsViewTests(TestCase):
    @mock.patch("mytvtime.views.find_tmdb_artwork")
    @mock.patch("mytvtime.views.search_shows_on_tvmaze")
    def test_search_results_prefer_tmdb_artwork(self, mock_search, mock_artwork):
        mock_search.return_value = TVMAZE_SEARCH_PAYLOAD
        mock_artwork.side_effect = [
            {"tmdb_id": 95396, "poster_url": "https://image.tmdb.org/t/p/w780/tmdb.jpg",
             "backdrop_url": "https://image.tmdb.org/t/p/w780/tmdb-backdrop.jpg"},
            None,  # second result stays on the TVmaze artwork
        ]

        response = self.client.post(
            reverse("mytvtime:search_results"), {"search_query": "severance"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://image.tmdb.org/t/p/w780/tmdb.jpg")
        # The result TMDB knows nothing about keeps the TVmaze poster.
        self.assertContains(response, "No Poster Show")
        # Both results are looked up on TMDB (by IMDb id first).
        self.assertEqual(mock_artwork.call_count, 2)
        self.assertEqual(mock_artwork.call_args_list[0].args[0], "tt11280740")

    @mock.patch("mytvtime.views.find_tmdb_artwork")
    @mock.patch("mytvtime.views.search_shows_on_tvmaze")
    def test_search_still_works_without_tmdb(self, mock_search, mock_artwork):
        mock_search.return_value = TVMAZE_SEARCH_PAYLOAD

        with mock.patch.object(views, "tmdb_api_key", None):
            response = self.client.post(
                reverse("mytvtime:search_results"), {"search_query": "severance"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, TVMAZE_SEARCH_PAYLOAD[0]["show"]["image"]["original"]
        )
        mock_artwork.assert_not_called()

    @mock.patch("mytvtime.views.find_tmdb_artwork")
    @mock.patch("mytvtime.views.search_shows_on_tvmaze")
    def test_search_failure_renders_empty_result_list(self, mock_search, mock_artwork):
        mock_search.return_value = []

        response = self.client.post(
            reverse("mytvtime:search_results"), {"search_query": "severance"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No search results found")
        mock_artwork.assert_not_called()


class UpdateShowInfoTests(TestCase):
    def setUp(self):
        self.show = Show.objects.create(
            tvmaze_id=44933, title="Old title", slug="old-title", status="ended"
        )

    def _show_details(self):
        details = views.normalize_tvmaze_show(TVMAZE_SHOW_PAYLOAD)
        details["next_episode"] = views.normalize_tvmaze_episode(
            TVMAZE_SHOW_PAYLOAD["_embedded"]["nextepisode"]
        )
        return details

    @mock.patch("mytvtime.views.get_show_artwork")
    @mock.patch("mytvtime.views.get_show_details_from_tvmaze")
    def test_updates_the_show_from_tvmaze_and_the_artwork_from_tmdb(self, mock_details, mock_artwork):
        mock_details.return_value = self._show_details()
        mock_artwork.return_value = TMDB_ARTWORK

        views.update_show_info(self.show)

        self.show.refresh_from_db()
        # TVmaze provides the data...
        self.assertEqual(self.show.title, "Severance")
        self.assertEqual(self.show.status, "returning series")
        self.assertEqual(self.show.imdb_id, "tt11280740")
        self.assertIsNotNone(self.show.tvmaze_updated_at)
        # ...and TMDB provides the artwork.
        self.assertEqual(self.show.tmdb_id, 95396)
        self.assertEqual(self.show.poster_url, TMDB_ARTWORK["poster_url"])
        self.assertEqual(self.show.backdrop_url, TMDB_ARTWORK["backdrop_url"])

        next_episode = self.show.next_episode
        self.assertEqual(next_episode.season, 3)
        self.assertEqual(next_episode.number, 1)
        self.assertEqual(
            next_episode.air_date, datetime(2026, 10, 15, 1, 0, tzinfo=dt_timezone.utc)
        )

    @mock.patch("mytvtime.views.get_show_artwork")
    @mock.patch("mytvtime.views.get_show_details_from_tvmaze")
    def test_falls_back_to_the_tvmaze_poster_when_tmdb_is_unavailable(self, mock_details, mock_artwork):
        mock_details.return_value = self._show_details()
        mock_artwork.return_value = None

        views.update_show_info(self.show)

        self.show.refresh_from_db()
        self.assertEqual(
            self.show.poster_url, TVMAZE_SHOW_PAYLOAD["image"]["original"]
        )

    @mock.patch("mytvtime.views.get_show_artwork")
    @mock.patch("mytvtime.views.get_show_details_from_tvmaze")
    def test_keeps_stored_artwork_when_tmdb_is_unavailable(self, mock_details, mock_artwork):
        self.show.poster_url = "https://image.tmdb.org/t/p/original/kept.jpg"
        self.show.backdrop_url = "https://image.tmdb.org/t/p/original/kept-backdrop.jpg"
        self.show.save()
        mock_details.return_value = self._show_details()
        mock_artwork.return_value = None

        views.update_show_info(self.show)

        self.show.refresh_from_db()
        self.assertEqual(self.show.poster_url, "https://image.tmdb.org/t/p/original/kept.jpg")
        self.assertEqual(
            self.show.backdrop_url, "https://image.tmdb.org/t/p/original/kept-backdrop.jpg"
        )

    @mock.patch("mytvtime.views.get_show_artwork")
    @mock.patch("mytvtime.views.get_show_details_from_tvmaze")
    def test_deletes_the_next_episode_when_the_show_has_none(self, mock_details, mock_artwork):
        NextEpisode.objects.create(show=self.show, season=2, number=9)
        details = self._show_details()
        details["next_episode"] = None
        mock_details.return_value = details
        mock_artwork.return_value = TMDB_ARTWORK

        views.update_show_info(self.show)

        self.assertFalse(NextEpisode.objects.filter(show=self.show).exists())

    @mock.patch("mytvtime.views.get_show_artwork")
    @mock.patch("mytvtime.views.get_show_details_from_tvmaze")
    def test_keeps_stored_values_when_tvmaze_has_no_data(self, mock_details, mock_artwork):
        mock_details.return_value = None

        views.update_show_info(self.show)

        self.show.refresh_from_db()
        self.assertEqual(self.show.title, "Old title")
        mock_artwork.assert_not_called()


class WatchlistViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="secret")
        self.client.force_login(self.user)

    def _show_details(self, tvmaze_id=44933, imdb_id="tt11280740"):
        details = views.normalize_tvmaze_show(TVMAZE_SHOW_PAYLOAD)
        details["tvmaze_id"] = tvmaze_id
        details["imdb_id"] = imdb_id
        details["next_episode"] = views.normalize_tvmaze_episode(
            TVMAZE_SHOW_PAYLOAD["_embedded"]["nextepisode"]
        )
        return details

    @mock.patch("mytvtime.views.get_show_artwork")
    @mock.patch("mytvtime.views.get_show_details_from_tvmaze")
    def test_add_show_to_watchlist_stores_tvmaze_data_and_tmdb_artwork(self, mock_details, mock_artwork):
        mock_details.return_value = self._show_details()
        mock_artwork.return_value = TMDB_ARTWORK

        response = self.client.get(reverse("mytvtime:add_to_watchlist", args=[44933]))

        self.assertRedirects(response, reverse("mytvtime:index"))
        show = Show.objects.get(tvmaze_id=44933)
        self.assertEqual(show.title, "Severance")
        self.assertEqual(show.tmdb_id, 95396)
        self.assertEqual(show.poster_url, TMDB_ARTWORK["poster_url"])
        self.assertEqual(show.backdrop_url, TMDB_ARTWORK["backdrop_url"])
        self.assertEqual(show.users.first(), self.user)
        self.assertTrue(Watchlist.objects.filter(user=self.user, show=show).exists())
        self.assertEqual(show.next_episode.season, 3)

    @mock.patch("mytvtime.views.get_show_artwork")
    @mock.patch("mytvtime.views.get_show_details_from_tvmaze")
    def test_add_show_falls_back_to_the_tvmaze_poster(self, mock_details, mock_artwork):
        mock_details.return_value = self._show_details()
        mock_artwork.return_value = None

        self.client.get(reverse("mytvtime:add_to_watchlist", args=[44933]))

        show = Show.objects.get(tvmaze_id=44933)
        self.assertEqual(show.poster_url, TVMAZE_SHOW_PAYLOAD["image"]["original"])
        self.assertIsNone(show.tmdb_id)

    @mock.patch("mytvtime.views.update_show_info")
    @mock.patch("mytvtime.views.get_show_details_from_tvmaze")
    def test_add_show_prefers_the_row_with_the_same_imdb_id(self, mock_details, mock_update):
        existing = Show.objects.create(
            tvmaze_id=111, imdb_id="tt11280740", title="Duplicate TVmaze entry", slug="dup"
        )
        mock_details.return_value = self._show_details(tvmaze_id=999)

        self.client.get(reverse("mytvtime:add_to_watchlist", args=[999]))

        self.assertEqual(Show.objects.count(), 1)
        self.assertTrue(Watchlist.objects.filter(user=self.user, show=existing).exists())
        mock_update.assert_called_once_with(existing)

    @mock.patch("mytvtime.views.get_show_details_from_tvmaze")
    def test_add_show_redirects_when_tvmaze_knows_nothing_about_the_id(self, mock_details):
        mock_details.return_value = None

        response = self.client.get(reverse("mytvtime:add_to_watchlist", args=[999999]))

        self.assertRedirects(response, reverse("mytvtime:index"))
        self.assertEqual(Show.objects.count(), 0)

    def test_get_watching_shows_exposes_tvmaze_ids_and_backdrops(self):
        show = Show.objects.create(
            tvmaze_id=44933, title="Severance", slug="severance", status="returning series",
            poster_url="https://image.tmdb.org/t/p/original/p.jpg",
            backdrop_url="https://image.tmdb.org/t/p/original/b.jpg",
        )
        show.users.add(self.user)
        NextEpisode.objects.create(
            show=show,
            title="Cold Harbor",
            season=3,
            number=1,
            air_date=datetime(2099, 1, 1, 1, 0, tzinfo=dt_timezone.utc),
        )
        Watchlist.objects.create(user=self.user, show=show)

        response = self.client.get("/get_watching_shows/")

        self.assertEqual(response.status_code, 200)
        watching_show = response.json()["watching_shows"][0]
        self.assertEqual(watching_show["tvmaze_id"], 44933)
        self.assertEqual(watching_show["status"], "Returning")
        self.assertEqual(watching_show["season"], 3)
        self.assertEqual(watching_show["episode"], 1)
        self.assertEqual(watching_show["poster_url"], show.poster_url)
        self.assertEqual(watching_show["backdrop_url"], show.backdrop_url)

    def test_remove_show_from_watchlist_deletes_the_untracked_show(self):
        show = Show.objects.create(tvmaze_id=44933, title="Severance", slug="severance")
        show.users.add(self.user)
        Watchlist.objects.create(user=self.user, show=show)

        response = self.client.post(
            "/remove_from_watchlist/",
            data=json.dumps({"tvmaze_id": 44933}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertFalse(Watchlist.objects.filter(user=self.user).exists())
        self.assertFalse(Show.objects.filter(tvmaze_id=44933).exists())

    def test_remove_show_rejects_a_payload_without_a_tvmaze_id(self):
        response = self.client.post(
            "/remove_from_watchlist/",
            data=json.dumps({"trakt_id": 44933}),
            content_type="application/json",
        )

        self.assertEqual(response.json()["status"], "error")
