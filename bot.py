# ============================================
# LAST.FM → DISCORD RANKING TRACKER
# ============================================

import json
import os
import time

import requests


# ============================================
# CONFIGURATION
# ============================================

LASTFM_USERNAME = os.environ["LASTFM_USERNAME"]
LASTFM_API_KEY = os.environ["LASTFM_API_KEY"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

# Turn each tracker ON or OFF
TRACK_ARTISTS = True
TRACK_ALBUMS = True
TRACK_TRACKS = True

# Last.fm API settings
LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"
PAGE_SIZE = 200

# Request settings
REQUEST_TIMEOUT = 30
MAX_RETRIES = 5

# Discord settings
DISCORD_MAX_LENGTH = 1900
DISCORD_DELAY = 0.5


# ============================================
# FILES
# ============================================

STATE_FILE = "ranking_state.json"


# ============================================
# LAST.FM REQUEST HELPER
# ============================================

def lastfm_request(params):
    """
    Make a request to the Last.fm API with retries.

    Returns:
        dict on success
        None on failure
    """

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = requests.get(
                LASTFM_URL,
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            response.raise_for_status()

            data = response.json()

            # Last.fm API-level error
            if "error" in data:

                error_code = data.get("error")
                error_message = data.get("message", "Unknown Last.fm error")

                print(
                    f"Last.fm error "
                    f"(attempt {attempt}/{MAX_RETRIES}): "
                    f"[{error_code}] {error_message}"
                )

                if attempt < MAX_RETRIES:

                    wait_time = attempt * 5

                    print(
                        f"Retrying in {wait_time} seconds..."
                    )

                    time.sleep(wait_time)

                    continue

                return None

            return data

        except requests.RequestException as error:

            print(
                f"Last.fm connection error "
                f"(attempt {attempt}/{MAX_RETRIES}): {error}"
            )

        except ValueError as error:

            print(
                f"Last.fm returned invalid JSON "
                f"(attempt {attempt}/{MAX_RETRIES}): {error}"
            )

        if attempt < MAX_RETRIES:

            wait_time = attempt * 5

            print(
                f"Retrying in {wait_time} seconds..."
            )

            time.sleep(wait_time)

    return None


# ============================================
# LAST.FM PAGINATION HELPER
# ============================================

def get_all_lastfm_pages(method, result_key, item_name):
    """
    Retrieve all pages from a Last.fm user ranking endpoint.

    Returns:
        list on success
        None on failure
    """

    items = []
    page = 1

    while True:

        params = {
            "method": method,
            "user": LASTFM_USERNAME,
            "api_key": LASTFM_API_KEY,
            "format": "json",
            "limit": PAGE_SIZE,
            "page": page,
            "period": "overall"
        }

        data = lastfm_request(params)

        if data is None:

            print(
                f"❌ Failed to retrieve {item_name}, "
                f"page {page}."
            )

            return None

        if result_key not in data:

            print(
                f"❌ Unexpected Last.fm response while getting "
                f"{item_name}, page {page}:"
            )

            print(data)

            return None

        result = data[result_key]

        batch = result.get(item_name, [])

        # Last.fm can occasionally return a single object
        # instead of a list when only one item exists.
        if isinstance(batch, dict):

            batch = [batch]

        if not batch:

            break

        items.extend(batch)

        attributes = result.get("@attr", {})

        try:
            total_pages = int(
                attributes.get("totalPages", page)
            )
        except (TypeError, ValueError):
            total_pages = page

        print(
            f"{item_name.capitalize()}: "
            f"page {page}/{total_pages}"
        )

        if page >= total_pages:

            break

        page += 1

    return items


# ============================================
# LAST.FM API
# ============================================

def get_top_artists():
    """Get all artists from your Last.fm library."""

    return get_all_lastfm_pages(
        method="user.gettopartists",
        result_key="topartists",
        item_name="artist"
    )


def get_top_albums():
    """Get all albums from your Last.fm library."""

    return get_all_lastfm_pages(
        method="user.gettopalbums",
        result_key="topalbums",
        item_name="album"
    )


def get_top_tracks():
    """Get all tracks from your Last.fm library."""

    return get_all_lastfm_pages(
        method="user.gettoptracks",
        result_key="toptracks",
        item_name="track"
    )


# ============================================
# RANKING PROCESSING
# ============================================

def make_ranking(items, category):
    """
    Convert Last.fm API results into a ranking dictionary.

    Example:

    {
        "Radiohead": {
            "position": 1,
            "scrobbles": 12345
        }
    }
    """

    ranking = {}

    if not items:
        return ranking

    for position, item in enumerate(items, start=1):

        try:

            if category == "artist":

                name = item["name"]

            elif category == "album":

                artist = item.get("artist", {}).get("name", "Unknown Artist")
                album = item.get("name", "Unknown Album")

                name = f"{artist} - {album}"

            elif category == "track":

                artist = item.get("artist", {}).get("name", "Unknown Artist")
                track = item.get("name", "Unknown Track")

                name = f"{artist} - {track}"

            else:

                continue

            playcount = int(
                item.get("playcount", 0)
            )

        except (KeyError, TypeError, ValueError) as error:

            print(
                f"⚠️ Could not process {category} at "
                f"position {position}: {error}"
            )

            continue

        ranking[name] = {
            "position": position,
            "scrobbles": playcount
        }

    return ranking


# ============================================
# RANKING COMPARISON
# ============================================

def compare_rankings(old, new, category):

    category_names = {
        "artist": "🎤 ARTIST",
        "album": "💿 ALBUM",
        "track": "🎵 TRACK"
    }

    movements = []

    for name, current in new.items():

        if name not in old:
            continue

        old_position = old[name]["position"]
        new_position = current["position"]

        # Only report items that moved UP
        if new_position >= old_position:
            continue

        movement = old_position - new_position

        overtaken = []

        for other_name, other_old in old.items():

            if other_name == name:
                continue

            if other_name not in new:
                continue

            other_old_position = other_old["position"]
            other_new_position = new[other_name]["position"]

            # Other item used to be ahead,
            # but is now behind.
            if (
                other_old_position < old_position
                and other_new_position > new_position
            ):

                overtaken.append({
                    "name": other_name,
                    "scrobbles": new[other_name]["scrobbles"],
                    "position": other_new_position
                })

        # Sort by new ranking position
        overtaken.sort(
            key=lambda x: x["position"]
        )

        scrobble_change = (
            current["scrobbles"]
            - old[name]["scrobbles"]
        )

        movements.append({
            "name": name,
            "old_position": old_position,
            "new_position": new_position,
            "movement": movement,
            "scrobbles": current["scrobbles"],
            "scrobble_change": scrobble_change,
            "overtaken": overtaken
        })

    if not movements:
        return

    # Biggest ranking jumps first
    movements.sort(
        key=lambda x: x["movement"],
        reverse=True
    )

    category_label = category_names.get(
        category,
        category.upper()
    )

    for move in movements:

        # Handle negative scrobble differences gracefully.
        if move["scrobble_change"] > 0:

            change_text = (
                f"(+{move['scrobble_change']:,})"
            )

        elif move["scrobble_change"] < 0:

            change_text = (
                f"({move['scrobble_change']:,})"
            )

        else:

            change_text = "(no change)"

        message = (
            f"{category_label}\n"
            f"🚨 **{move['name']}**\n"
            f"🎧 **{move['scrobbles']:,} scrobbles** "
            f"{change_text}\n"
            f"📈 **#{move['old_position']} → "
            f"#{move['new_position']}** "
            f"(+{move['movement']})"
        )

        if move["overtaken"]:

            overtaken_count = len(
                move["overtaken"]
            )

            if overtaken_count > 10:

                plural = (
                    category
                    if category.endswith("s")
                    else f"{category}s"
                )

                message += (
                    f"\n⬆️ **Overtook "
                    f"{overtaken_count} {plural}**"
                )

            else:

                message += "\n⬆️ **Overtook:**"

                for item in move["overtaken"]:

                    message += (
                        f"\n• #{item['position']} "
                        f"**{item['name']}** "
                        f"({item['scrobbles']:,} scrobbles)"
                    )

        send_discord(message)


# ============================================
# DISCORD
# ============================================

def split_discord_message(message):
    """
    Split a message into Discord-safe chunks.
    """

    lines = message.split("\n")

    chunks = []
    current = ""

    for line in lines:

        # Normal case
        if (
            len(current)
            + len(line)
            + 1
            <= DISCORD_MAX_LENGTH
        ):

            current += line + "\n"

            continue

        # Save current chunk
        if current.strip():

            chunks.append(
                current.rstrip()
            )

        # Handle an individual line
        while len(line) > DISCORD_MAX_LENGTH:

            chunks.append(
                line[:DISCORD_MAX_LENGTH]
            )

            line = line[
                DISCORD_MAX_LENGTH:
            ]

        current = line + "\n"

    if current.strip():

        chunks.append(
            current.rstrip()
        )

    return chunks


def send_discord(message):
    """
    Send a message to Discord with retry handling.
    """

    chunks = split_discord_message(message)

    for chunk in chunks:

        for attempt in range(
            1,
            MAX_RETRIES + 1
        ):

            try:

                response = requests.post(
                    DISCORD_WEBHOOK_URL,
                    json={
                        "content": chunk
                    },
                    timeout=REQUEST_TIMEOUT
                )

                # Successful Discord webhook
                if response.status_code in (200, 204):

                    break

                # Rate limited
                if response.status_code == 429:

                    retry_after = 5

                    try:

                        retry_data = response.json()

                        retry_after = float(
                            retry_data.get(
                                "retry_after",
                                5
                            )
                        )

                    except (ValueError, TypeError):

                        pass

                    print(
                        f"Discord rate limit. "
                        f"Waiting {retry_after} seconds..."
                    )

                    time.sleep(
                        retry_after
                    )

                    continue

                # Other HTTP error
                print(
                    f"Discord error "
                    f"(attempt {attempt}/{MAX_RETRIES}): "
                    f"{response.status_code} "
                    f"{response.text}"
                )

            except requests.RequestException as error:

                print(
                    f"Discord connection error "
                    f"(attempt {attempt}/{MAX_RETRIES}): "
                    f"{error}"
                )

            if attempt < MAX_RETRIES:

                wait_time = attempt * 2

                time.sleep(
                    wait_time
                )

            else:

                print(
                    "❌ Failed to send Discord message."
                )

        # Small delay between messages
        time.sleep(
            DISCORD_DELAY
        )


# ============================================
# LOAD / SAVE
# ============================================

def load_state():

    if not os.path.exists(STATE_FILE):

        print(
            "No previous ranking state found."
        )

        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            state = json.load(file)

        if not isinstance(state, dict):

            print(
                "⚠️ Ranking state is not a dictionary."
            )

            return {}

        return state

    except (
        OSError,
        json.JSONDecodeError
    ) as error:

        print(
            f"⚠️ Could not load ranking state: {error}"
        )

        return {}


def save_state(state):

    # Write to a temporary file first.
    # This prevents a partially-written state file.
    temp_file = f"{STATE_FILE}.tmp"

    try:

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                state,
                file,
                indent=2,
                ensure_ascii=False
            )

        os.replace(
            temp_file,
            STATE_FILE
        )

        print(
            "Ranking state saved."
        )

    except OSError as error:

        print(
            f"❌ Could not save ranking state: {error}"
        )

        # Try to clean up temporary file
        try:

            if os.path.exists(temp_file):

                os.remove(temp_file)

        except OSError:

            pass

        raise


# ============================================
# MAIN RANKING CHECK
# ============================================

def check_rankings():

    print()
    print("Loading previous ranking state...")

    old_state = load_state()

    new_state = {}

    # ========================================
    # ARTISTS
    # ========================================

    if TRACK_ARTISTS:

        print()
        print("Getting artists...")

        artists = get_top_artists()

        if artists is not None:

            new_state["artists"] = make_ranking(
                artists,
                "artist"
            )

            print(
                f"Loaded {len(new_state['artists']):,} artists."
            )

            if "artists" in old_state:

                compare_rankings(
                    old_state["artists"],
                    new_state["artists"],
                    "artist"
                )

        else:

            print(
                "⚠️ Artist data could not be retrieved."
            )

            # Keep previous ranking
            if "artists" in old_state:

                new_state["artists"] = (
                    old_state["artists"]
                )

    # ========================================
    # ALBUMS
    # ========================================

    if TRACK_ALBUMS:

        print()
        print("Getting albums...")

        albums = get_top_albums()

        if albums is not None:

            new_state["albums"] = make_ranking(
                albums,
                "album"
            )

            print(
                f"Loaded {len(new_state['albums']):,} albums."
            )

            if "albums" in old_state:

                compare_rankings(
                    old_state["albums"],
                    new_state["albums"],
                    "album"
                )

        else:

            print(
                "⚠️ Album data could not be retrieved."
            )

            # Keep previous ranking
            if "albums" in old_state:

                new_state["albums"] = (
                    old_state["albums"]
                )

    # ========================================
    # TRACKS
    # ========================================

    if TRACK_TRACKS:

        print()
        print("Getting tracks...")

        tracks = get_top_tracks()

        if tracks is not None:

            new_state["tracks"] = make_ranking(
                tracks,
                "track"
            )

            print(
                f"Loaded {len(new_state['tracks']):,} tracks."
            )

            if "tracks" in old_state:

                compare_rankings(
                    old_state["tracks"],
                    new_state["tracks"],
                    "track"
                )

        else:

            print(
                "⚠️ Track data could not be retrieved."
            )

            # Keep previous ranking
            if "tracks" in old_state:

                new_state["tracks"] = (
                    old_state["tracks"]
                )

    # ========================================
    # SAVE STATE
    # ========================================

    save_state(new_state)

    # ========================================
    # COMPLETION MESSAGE
    # ========================================

    send_discord(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ **RANKING CHECK COMPLETE**\n"
        "🕐 Next check in **~10 minutes**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


# ============================================
# RUN ONCE
# ============================================

print("============================================")
print(" Last.fm Ranking Tracker")
print("============================================")
print()
print("Artists:", TRACK_ARTISTS)
print("Albums :", TRACK_ALBUMS)
print("Tracks :", TRACK_TRACKS)
print()

try:

    print("Checking Last.fm...")

    check_rankings()

    print()
    print("Done!")

except Exception as error:

    print()
    print("============================================")
    print(" ERROR")
    print("============================================")
    print(error)

    raise
