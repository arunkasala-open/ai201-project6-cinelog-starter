# PR Response Doc - CineLog Watchlist Feature

## AI Usage

I used an AI assistant to *understand* existing code before writing my own, not to
write the changes for me. Specifically, I asked it to walk me through
`add_to_collection()` in `services/collection_service.py` — what its deduplication
check does and what it returns/raises when a duplicate is found — and to explain the
test patterns in `tests/test_collection.py`. I then wrote the deduplication check in
`add_to_watchlist()` and the new test myself, modeled on those patterns.

For Comments 4 and 5, I used AI as a **devil's advocate**. I wrote my own drafts
first, then asked: "What is the single strongest counterargument a careful maintainer
would raise, and what tradeoff am I not acknowledging?" It surfaced two real gaps that
changed my responses:
- On Comment 4, it pointed out that my "consistency with already-public collections"
  argument *levels privacy down to a broken baseline* — in a no-auth app, `public=True`
  is a second unauthenticated leak of intent data, and a user-level privacy toggle
  can't even be built without auth. I reversed my position to private-by-default and
  dropped the consistency argument.
- On Comment 5, it caught that my "recently added = top of mind" reasoning is
  *collection* logic; for a watchlist (a queue), newest-first inverts queue priority.
  I rewrote the argument to give FIFO/oldest-first genuine weight instead of dismissing
  it, and to justify my default on honest grounds rather than "consistency."
The final arguments below are my own reasoning grounded in CineLog's context; AI only
pressure-tested the drafts.

Finally, during history cleanup I gave my `git log --oneline` to an AI tool and asked
whether every message followed Conventional Commits and whether any commit bundled
multiple logical changes. It flagged two real problems, which I acted on after checking
them against the spec myself: (1) my rename commit was typed `fix:` when a pure rename
with no behavior change is a `refactor:`, and (2) the inherited `db.session.get` commit
bundled *two* unrelated changes — the retrieval swap **and** an app.py circular-import
fix — behind a subject that mentioned only the former. I split it: the circular-import
fix now lives in the `feat` commit that introduced the bad import, leaving a clean
`refactor: use db.session.get for film retrieval`. I kept the dedup commit as `fix:`
(closing a missing-guard defect) despite the AI suggesting `feat:`, because that matches
how the review framed it and CineLog's commit conventions.

## Comment 1 - Rename

**What I did:**
Renamed `save_to_watchlist()` to `add_to_watchlist()` in
`services/watchlist_service.py` (and updated its docstring "Save" → "Add"). Updated
the one call site in `routes/watchlist/watchlist.py`: both the import on line 8 and
the call on line 32.

**How I Verified:**
Ran a project-wide search (`grep -rn "save_to_watchlist" .`) before and after the
change. Before: 3 hits (the definition, the import, the call). After: 0 hits, and
`grep -rn "add_to_watchlist"` shows exactly the 3 expected references (definition +
import + call). Then ran `pytest tests/ -v` — all 4 existing tests still pass, so no
call site was missed.

## Comment 2 — Deduplication

**Model I followed:**
`add_to_collection()` in `services/collection_service.py` (lines 47–53). After the
film-exists check it runs
`CollectionEntry.query.filter_by(user_id=..., film_id=...).first()` and, if that
returns a row, raises `AlreadyInCollectionError` (it returns nothing on the duplicate
path — the caller is expected to handle the exception).

**What I did:**
Added the same guard to `add_to_watchlist()`, placed after the `FilmNotFoundError`
check and before creating the entry. I defined a watchlist-specific exception
`AlreadyInWatchlistError` in `services/watchlist_service.py`, mirroring how the
collection service defines its own `AlreadyInCollectionError`, and documented it in the
function's `Raises:` docstring. Note this matters here because, unlike
`CollectionEntry`, `WatchlistEntry` has **no** DB-level unique constraint in
`models.py`, so this in-code check is the only thing preventing duplicate rows.

**How I verified:**
Wrote a small throwaway script that adds the same (user, film) twice: the second call
raised `AlreadyInWatchlistError`, only **one** `WatchlistEntry` row existed afterward,
and adding a nonexistent `film_id` still raised `FilmNotFoundError` (confirming I
didn't break the earlier guard). Then ran `pytest tests/ -v` — all 4 tests pass.

## Comment 3 — Missing test

**Test I used as my model:**
`test_add_to_collection_nonexistent_film_raises` in `tests/test_collection.py`
(lines 98–107). I copied its structure: the `app` fixture (isolated in-memory SQLite,
`db.create_all()` / `drop_all()` teardown) and the `sample_user` fixture that returns
`user.id`, then the `with pytest.raises(FilmNotFoundError):` assertion.

**What I did:**
Created `tests/test_watchlist.py` with the `app` and `sample_user` fixtures (no
`sample_film` fixture needed — the whole point is that the film does *not* exist) and
`test_add_to_watchlist_nonexistent_film_raises`, which calls `add_to_watchlist` with a
film id that was never inserted and asserts `FilmNotFoundError` is raised. I used a
nonexistent integer id (`999999`) rather than the collection test's UUID string,
because on this pre-refactor branch `Film.id` is still an integer PK, so an integer
makes the "does not exist" intent unambiguous.

**How I verified:**
`pytest tests/test_watchlist.py -v` → 1 passed. `pytest tests/ -v` → 5 passed
(4 existing + the new one), confirming nothing else broke.

## Comment 4 — Default visibility

**My position:**
I disagree with the current `public=True` default. Watchlists should default to
**private (`public=False`)**, with sharing as an explicit opt-in.

**Reasoning — what user behavior I'm optimizing for:**
I'm optimizing for *the principle of least surprise* and protecting predictive user
data. A watchlist is forward-looking *intent* — films a user plans to watch but hasn't.
That's meaningfully more sensitive than a collection (a log of what they've already
watched): intent reveals taste the user may be undecided about or embarrassed by, and
they may never act on it. Publishing that by default, silently, is the kind of thing
users only discover after the fact — and that erodes trust in a community app faster
than a missing feature does.

The no-auth reality of CineLog makes this sharper, not softer. Today `public=True`
isn't really a "social discovery" feature — there's no follow/friend graph in the
schema, so nobody's watchlist surfaces to anybody through relationships. What
`public=True` actually does is expose a *second* unauthenticated read surface: anyone
who can guess or enumerate a `user_id` can read a stranger's future-viewing intentions
with no login. Defaulting that on is opt-out surveillance of intent, and the
"discovery" upside it's supposed to buy doesn't exist yet.

I explicitly reject the tempting counter-argument that "collections are already openly
viewable, so watchlists should match." That reasons from a broken baseline. The right
conclusion from "collections leak by user_id with no auth" is that CineLog's privacy
posture already needs fixing — not that we should extend the leak to more-sensitive
data for the sake of consistency.

**Tradeoff acknowledged:**
Private-by-default does cut against CineLog's stated identity as a *community* app.
Public watchlists are exactly the raw material a future recommendation/social-discovery
feature would want, and an opt-in default means most users never flip the switch, so
that corpus stays small — a real cost to network effects. I accept that cost because
the discovery feature is hypothetical today while the intent-leak is real today, and
because the safe default is the reversible one: users can always be nudged to share,
but you can't un-leak data that was public by default.

**Scope note (why this is a written recommendation, not a code change here):**
The minimal change is flipping the column default to `False`. I've kept it as a
documented recommendation rather than shipping it in this PR because a *robust*
visibility model needs authentication first — without a logged-in identity there's no
one to attach a privacy setting to and no way to prove ownership when toggling it. I'd
also argue visibility belongs at the user/list level, not as a per-*entry* `public`
boolean (the current granularity means a user sets visibility one film at a time, which
no one will do consistently). Both of those depend on auth landing first, so I'm
flagging the default as wrong and proposing `public=False` + user-level control as the
follow-up, rather than shipping a per-entry half-measure that gives false assurance.

## Comment 5 — Sort order

**My position:**
Partially agree with the maintainer. They're right that alphabetical is the wrong sort
and that **date-added** is the correct axis, so I've changed `get_watchlist()` from
`Film.title.asc()` to sort by `date_added`. I'm defaulting to **newest-first**
(matching `get_collection()`), but I want to be honest that this is a judgment call on
*direction*, not a free win from "consistency" — and I'm proposing a `?sort=` param as
the real long-term answer.

**Reasoning:**
Alphabetical order carries no signal about user intent — where a film sorts depends on
its title, which the user didn't choose and doesn't care about when scanning their
list. Date-added at least encodes something the user did. So the maintainer's instinct
to drop alphabetical is correct.

The genuinely hard part is direction, and here I have to be careful not to borrow
collection logic. A collection is a backward-looking *log*: the most recent thing you
did is the most relevant, so newest-first is obviously right. A watchlist is a
forward-looking *queue*, and for a queue there's a strong case for **oldest-first
(FIFO)**: the films you've been meaning to watch longest are the ones most at risk of
being forgotten, and newest-first buries them under every impulse-add — that's how
watchlists rot. I don't think that argument is weak, and I'm not dismissing it.

I still choose newest-first as the *default* for three concrete reasons: (1) the most
common immediate action on a watchlist is "I just added something — let me find it
again," which newest-first serves directly; (2) it matches the dominant pattern users
already expect from consumer watch-queues; (3) it's the lower-risk, reversible default.
But because the FIFO case is real, the honest resolution isn't to pick one order and
call it correct — it's to add a `?sort=date_added&order=asc|desc` query param (mirroring
how `/films/` already takes query filters) so backlog-clearers can get oldest-first.
I'm proposing that as a follow-up rather than building it in this PR to keep the change
focused; the default flip from alphabetical → newest-first is the part I've shipped.

**Engagement with reviewer's point:**
The maintainer's core reasoning is *consistency* with `get_collection()`. I want to
push back on that specific justification even while landing on the same sort order:
consistency between two endpoints is only a virtue when the endpoints model the same
kind of thing. A log and a queue have opposite temporal semantics, so "make them match"
is not, by itself, a reason — if I'd followed consistency mechanically I'd never have
noticed the FIFO argument. I'm adopting date-added because recency beats alphabetical
as an intent signal, and newest-first because of the concrete UX reasons above — not
because collection does it. That distinction is what makes me comfortable that
newest-first is a defensible default and that the `?sort=` escape hatch is the right
next step rather than an afterthought.

**How I verified:**
I exercised the exact query my change controls — `filter_by(...).order_by(
WatchlistEntry.date_added.desc())` — with two entries added five days apart, and
confirmed the newer one comes back first. `pytest tests/ -v` still passes (5 tests).

**Separate pre-existing bug I found — now FIXED (see "Follow-up fixes" below):**
While verifying, I discovered `get_watchlist()` raises `AttributeError:
'WatchlistEntry' object has no attribute 'film'` for *any* non-empty watchlist — the
committed HEAD version had the same defect, so my sort change didn't introduce it.
Root cause: in `models.py`, `Film` declared a `backref="film"` only for
`CollectionEntry`, so `CollectionEntry.film` existed but `WatchlistEntry.film` did not,
and `get_watchlist()` calls `entry.film.to_dict()`. I originally flagged this as
out-of-scope, but per reviewer feedback I shipped the one-line fix (adding the missing
`watchlist_entries` relationship to `Film`). Details under **Follow-up fixes**.

## Comment 6 — Rebase

**Process:**
`git fetch origin`, then `git rebase origin/main`. (Before rebasing I created a
`backup/feature-watchlist-pre-rebase` branch so I could recover if anything went
wrong.) The rebase initially aborted because an untracked local `.gitignore` would
have been overwritten by main's tracked one; I moved my local copy aside and re-ran,
after which all six commits replayed and the branch history is linear.

**What conflicted:**
Interestingly, there was **no textual merge conflict** — and that was the trap. None
of my six commits ever modified `models.py`; `WatchlistEntry` lived in `models.py`
purely because it was present at the branch's base commit. Main's UUID refactor
(`refactor: migrate film IDs from integer to UUID`) rewrote `models.py`: it changed
`Film.id` and `CollectionEntry.film_id` from `Integer` to `String(36)` **and deleted
the `WatchlistEntry` class entirely.** Because my commits didn't touch `models.py`,
git had nothing to three-way-merge and simply took main's version wholesale. The
result: a clean rebase that silently **dropped `WatchlistEntry`**, so
`from models import ... WatchlistEntry` raised `ImportError` and the whole watchlist
feature was broken. This is the "UUID conflict" — semantic, not a `<<<<<<<` marker.

**How I resolved it:**
I updated the watchlist code to match the post-refactor UUID world:
1. Re-added the `WatchlistEntry` model to `models.py`, changing its `film_id` from
   `db.Integer` to `db.String(36)` (a UUID FK to `film.id`) so it lines up with
   main's `Film.id` and `CollectionEntry.film_id`.
2. Updated the docstring in `services/watchlist_service.py` from
   `film_id (int): ... pre-refactor` to `film_id (str): UUID of the film`.
3. Updated the route docstring in `routes/watchlist/watchlist.py` from
   `Body: { "film_id": <int> }` to a UUID.
4. Updated `tests/test_watchlist.py`: the "nonexistent film" id went from the integer
   `999999` to a UUID string `00000000-0000-0000-0000-000000000000`, matching the
   post-refactor schema (and now consistent with `test_collection.py`).

**How I verified no conflict remains:**
- `git status` → clean; `git rebase` exited 0.
- **No merge commits in my branch:** `git log --merges origin/main..HEAD` returns
  nothing — all six of my commits are non-merge and sit linearly on top of main.
  (The only merge commit reachable, `bbe206c`, belongs to `origin/main` itself; it's
  upstream history, not something this PR introduced.)
- The app imports cleanly again, and `WatchlistEntry.film_id` is `VARCHAR(36)`.
- End-to-end: created a `Film` (whose id is now a real UUID), called
  `add_to_watchlist` with it — the entry's `film_id` matched the UUID, and the
  duplicate/`FilmNotFoundError` guards still fired.
- `pytest tests/ -v` → all 5 tests pass.

## Commit History

Final `git log --oneline` for this branch (feature/watchlist → main), rebased on
`origin/main` with a linear, conventional history and no merge commits:

> _Screenshot of `git log --oneline` (rendered as text — this is the verbatim
> terminal output):_

```text
$ git log --oneline origin/main..HEAD
585956a docs: add pr-response with review responses and design decisions
1aad776 fix: restore WatchlistEntry model with UUID film_id after main rebase
714ca86 fix: sort watchlist by date added instead of alphabetically
77caf25 test: add test for nonexistent film_id in add_to_watchlist
3d0acb6 fix: add deduplication check to prevent duplicate watchlist entries
89ec46c refactor: rename save_to_watchlist to add_to_watchlist
4c1b026 refactor: use db.session.get for film retrieval
c80bc8d feat: add watchlist endpoint and service
```

Eight commits, all Conventional Commits format (`feat` / `fix` / `refactor` / `test` /
`docs`), each a single logical change, no merge commits. (The `docs:` line's own
short-hash shifts by one when this file is committed — a commit can't embed its own
final hash — but the seven commits beneath it are stable.)

## PR Description

### What this feature does

Adds a **watchlist** to CineLog: a per-user list of films a user intends to watch
later (distinct from a *collection*, which logs films already watched). It introduces:

- A `WatchlistEntry` model (`user_id`, `film_id` as a UUID FK, `date_added`, and a
  `public` visibility flag).
- A service layer (`services/watchlist_service.py`): `add_to_watchlist(user_id,
  film_id)` and `get_watchlist(user_id)`. `add_to_watchlist` raises `FilmNotFoundError`
  for an unknown film and `AlreadyInWatchlistError` if the film is already on the list.
- Two endpoints (`routes/watchlist/watchlist.py`): `POST /watchlist/<user_id>/add`
  (body `{"film_id": "<uuid>"}`) and `GET /watchlist/<user_id>`.

### Design decisions

1. **Visibility default (Comment 4).** I argue the `public` flag should default to
   **`False` (private)**, not `True`. A watchlist exposes forward-looking *intent*,
   which is more sensitive than a log of already-watched films, and CineLog currently
   has no auth — so `public=True` is an unauthenticated read surface for anyone who
   knows a `user_id`, not a real "social discovery" feature (there's no friend graph
   yet). Tradeoff: private-by-default weakens the community-discovery corpus. I've kept
   this as a **recommendation** rather than a code change, because a real visibility
   model needs authentication first and belongs at the user/list level, not the current
   per-entry flag. (Full reasoning under Comment 4.)

2. **Sort order (Comment 5).** `get_watchlist()` now sorts by **`date_added`
   descending (newest first)** instead of alphabetically by title. Alphabetical carries
   no intent signal; date-added does. I default to newest-first for consistency with
   `get_collection()` and because "find what I just added" is the common action — while
   acknowledging a watchlist is a *queue* where oldest-first (FIFO) is a legitimate
   default, and proposing a `?sort=` query param as the follow-up so both orders are
   available. (Full reasoning under Comment 5.)

### How to manually test

Prerequisites: `pip install -r requirements.txt`, then `python app.py` (starts on
`http://localhost:5000`, SQLite at `cinelog.db`).

Because CineLog has no user/film creation endpoints yet, seed one user and one film
first, then exercise the watchlist:

1. **Seed a user and a film** (from a Python shell in the project root):
   ```python
   from app import create_app, db
   from models import User, Film
   app = create_app()
   with app.app_context():
       u = User(username="alice", email="alice@example.com")
       f = Film(title="Dune", year=2021)
       db.session.add_all([u, f]); db.session.commit()
       print("USER_ID =", u.id, "\nFILM_ID =", f.id)   # both are UUIDs
   ```
2. **Add the film to the watchlist** (happy path → `201` with the new entry):
   ```bash
   curl -i -X POST http://localhost:5000/watchlist/<USER_ID>/add \
        -H "Content-Type: application/json" \
        -d '{"film_id": "<FILM_ID>"}'
   ```
   Expect HTTP `201` and a JSON body with `film_id` equal to `<FILM_ID>` and
   `public: true`.
3. **View the watchlist** → `200` with a JSON list (newest-added first):
   ```bash
   curl -i http://localhost:5000/watchlist/<USER_ID>
   ```
4. **Check the error paths:**
   - Re-run the POST from step 2 with the same `film_id` → **`409`** (already on the
     watchlist).
   - POST with a `film_id` that doesn't exist → **`404`** (film not found).
5. **Run the test suite** (covers all of the above plus the service-level guards):
   ```bash
   pytest tests/ -v      # 11 passed
   ```

### Follow-up fixes (shipped in this PR after reviewer feedback)

The reviewer noted that flagging a clearly-correct one-line fix without shipping it
leaves a known-broken endpoint in the PR. Agreed — I fixed both defects I had
originally flagged as out-of-scope:

- **`GET /watchlist/<user_id>` no longer errors on a non-empty list.** Added the missing
  `watchlist_entries = db.relationship("WatchlistEntry", backref="film", lazy=True)` to
  `Film` in `models.py`, which is what `get_watchlist()`'s `entry.film.to_dict()` needs.
  Verified: `GET /watchlist/<user_id>` now returns `200` with the film list, and a new
  `test_get_watchlist_returns_films_newest_first` test covers it.
- **The route now maps service exceptions to HTTP status codes.**
  `POST /watchlist/<user_id>/add` returns `404` for `FilmNotFoundError` and `409` for
  `AlreadyInWatchlistError` instead of surfacing `500`s. New route-level tests assert
  the `201` / `404` / `409` responses.

The test suite grew from 5 to **11 tests** (added happy-path add, duplicate, and
`get_watchlist` service tests plus the three route status-code tests), following the
happy-path / duplicate / nonexistent pattern `CONTRIBUTING.md` asks for.

### Remaining follow-ups (still out of scope)

- The **visibility default** (`public=False`) and the **`?sort=` param** described above
  are proposed follow-ups; the visibility change is gated on authentication landing
  first.
