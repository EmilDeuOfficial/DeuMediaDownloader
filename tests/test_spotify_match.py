import pytest

import downloader
from config import T


def entry(vid, duration):
    return {"id": vid, "duration": duration}


def fake_search(results):
    """results: {query_text: [entries]}; records the queries that were asked."""
    asked = []

    def search(query):
        asked.append(query)
        return results.get(query, [])

    return search, asked


def test_queries_start_with_full_artist_string_then_each_artist():
    assert downloader._search_queries("HARDX, NX!ZE", "ELECTROSOULS") == [
        "HARDX, NX!ZE - ELECTROSOULS",
        "HARDX - ELECTROSOULS",
        "NX!ZE - ELECTROSOULS",
    ]


def test_queries_for_single_artist_are_not_duplicated():
    assert downloader._search_queries("Daft Punk", "Get Lucky") == ["Daft Punk - Get Lucky"]


def test_falls_back_to_single_artist_when_joined_artists_find_nothing(monkeypatch):
    # Real case: "HARDX, NX!ZE - ELECTROSOULS" returns 0 results on YouTube, "HARDX - ..." returns 5.
    search, asked = fake_search({"HARDX - ELECTROSOULS": [entry("wrong", 300), entry("right", 142)]})
    monkeypatch.setattr(downloader, "_search_entries", search)
    url = downloader._find_best_youtube_match("HARDX, NX!ZE", "ELECTROSOULS", 141_000)
    assert url == "https://www.youtube.com/watch?v=right"
    assert asked == ["HARDX, NX!ZE - ELECTROSOULS", "HARDX - ELECTROSOULS"]


def test_stops_at_first_query_with_results(monkeypatch):
    search, asked = fake_search({"A, B - T": [entry("first", 100)], "A - T": [entry("later", 100)]})
    monkeypatch.setattr(downloader, "_search_entries", search)
    assert downloader._find_best_youtube_match("A, B", "T", 100_000).endswith("first")
    assert asked == ["A, B - T"]


def test_without_spotify_duration_takes_first_result(monkeypatch):
    search, _ = fake_search({"A - T": [entry("one", 10), entry("two", 99)]})
    monkeypatch.setattr(downloader, "_search_entries", search)
    assert downloader._find_best_youtube_match("A", "T", 0).endswith("one")


def test_no_result_for_any_query_raises_clear_error(monkeypatch):
    search, asked = fake_search({})
    monkeypatch.setattr(downloader, "_search_entries", search)
    with pytest.raises(LookupError) as exc:
        downloader._find_best_youtube_match("HARDX, NX!ZE", "ELECTROSOULS", 141_000)
    assert str(exc.value) == T("err_no_match").format("HARDX, NX!ZE - ELECTROSOULS")
    assert len(asked) == 3


def test_entries_without_duration_are_skipped_when_duration_known(monkeypatch):
    search, _ = fake_search({"A - T": [{"id": "nodur"}, entry("ok", 200)]})
    monkeypatch.setattr(downloader, "_search_entries", search)
    assert downloader._find_best_youtube_match("A", "T", 200_000).endswith("ok")
