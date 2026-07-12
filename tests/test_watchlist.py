"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service.
Modeled on tests/test_collection.py — same fixture and assertion structure.
"""

import pytest
from app import create_app, db
from models import User, Film, WatchlistEntry
from services.watchlist_service import (
    add_to_watchlist,
    get_watchlist,
    AlreadyInWatchlistError,
)
from services.collection_service import FilmNotFoundError


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    """A user to use in tests."""
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    """A film to use in tests."""
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


# ── Basic add ────────────────────────────────────────────────────────────────

def test_add_to_watchlist_creates_entry(app, sample_user, sample_film):
    """Adding a valid film should create a WatchlistEntry in the database."""
    with app.app_context():
        entry = add_to_watchlist(user_id=sample_user, film_id=sample_film)

        assert entry is not None
        assert entry.user_id == sample_user
        assert entry.film_id == sample_film

        in_db = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert in_db is not None


# ── Deduplication ────────────────────────────────────────────────────────────

def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    """
    Adding the same film twice should raise AlreadyInWatchlistError, not
    silently create a duplicate entry.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        with pytest.raises(AlreadyInWatchlistError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1


# ── Nonexistent film ─────────────────────────────────────────────────────────

def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that doesn't exist in the database should raise
    FilmNotFoundError, not a database integrity error.

    Equivalent of test_add_to_collection_nonexistent_film_raises.
    """
    with app.app_context():
        # Film.id is a UUID (post-refactor); this UUID was never inserted.
        nonexistent_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=nonexistent_film_id)


# ── get_watchlist ────────────────────────────────────────────────────────────

def test_get_watchlist_returns_films_newest_first(app, sample_user):
    """
    get_watchlist() should return the user's films (via the WatchlistEntry.film
    relationship) sorted by date_added descending (most recently added first).
    """
    with app.app_context():
        from datetime import datetime, timezone, timedelta

        film_a = Film(title="Alien", year=1979, genre="Horror")
        film_b = Film(title="Blade Runner", year=1982, genre="Sci-Fi")
        db.session.add_all([film_a, film_b])
        db.session.commit()

        earlier = datetime.now(timezone.utc) - timedelta(days=5)
        later = datetime.now(timezone.utc)

        db.session.add_all([
            WatchlistEntry(user_id=sample_user, film_id=film_a.id, date_added=earlier),
            WatchlistEntry(user_id=sample_user, film_id=film_b.id, date_added=later),
        ])
        db.session.commit()

        watchlist = get_watchlist(sample_user)
        titles = [f["title"] for f in watchlist]

        # Blade Runner was added later, so it should come first.
        assert titles == ["Blade Runner", "Alien"]


# ── Route: HTTP status mapping ───────────────────────────────────────────────

def test_add_film_endpoint_returns_201(app, sample_user, sample_film):
    """POST /watchlist/<user_id>/add returns 201 for a valid film."""
    with app.app_context():
        client = app.test_client()
        resp = client.post(
            f"/watchlist/{sample_user}/add", json={"film_id": sample_film}
        )
        assert resp.status_code == 201
        assert resp.get_json()["film_id"] == sample_film


def test_add_film_endpoint_returns_404_for_unknown_film(app, sample_user):
    """POST maps FilmNotFoundError to 404, not a 500."""
    with app.app_context():
        client = app.test_client()
        resp = client.post(
            f"/watchlist/{sample_user}/add",
            json={"film_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert resp.status_code == 404


def test_add_film_endpoint_returns_409_for_duplicate(app, sample_user, sample_film):
    """POST maps AlreadyInWatchlistError to 409, not a 500."""
    with app.app_context():
        client = app.test_client()
        client.post(f"/watchlist/{sample_user}/add", json={"film_id": sample_film})
        resp = client.post(
            f"/watchlist/{sample_user}/add", json={"film_id": sample_film}
        )
        assert resp.status_code == 409
