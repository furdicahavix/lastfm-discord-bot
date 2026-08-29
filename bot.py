# ============================================
# LAST.FM → DISCORD RANKING TRACKER
# ============================================

import requests
import json
import os
import time

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

# How often to check Last.fm (in minutes)
CHECK_INTERVAL = 10

# ============================================
# FILES
# ============================================

STATE_FILE = "ranking_state.json"


# ============================================
# LAST.FM API
# ============================================

def get_top_artists():
    """Get all artists from your Last.fm library."""
    artists = []
    page = 1

    while True:
        url = "https://ws.audioscrobbler.com/2.0/"

        params = {
            "method": "user.gettopartists",
            "user": LASTFM_USERNAME,
            "api_key": LASTFM_API_KEY,
            "format": "json",
            "limit": 200,
            "page": page,
            "period": "overall"
        }

        response = requests.get(url, params=params)
        data = response.json()

        if "topartists" not in data:
            print("Error getting artists:", data)
            break

        batch = data["topartists"]["artist"]

        if not batch:
            break

        artists.extend(batch)

        total_pages = int(data["topartists"]["@attr"]["totalPages"])

        print(f"Artists: page {page}/{total_pages}")

        if page >= total_pages:
            break

        page += 1

    return artists


def get_top_albums():
    """Get all albums from your Last.fm library."""
    albums = []
    page = 1

    while True:
        url = "https://ws.audioscrobbler.com/2.0/"

        params = {
            "method": "user.gettopalbums",
            "user": LASTFM_USERNAME,
            "api_key": LASTFM_API_KEY,
            "format": "json",
            "limit": 200,
            "page": page,
            "period": "overall"
        }

        response = requests.get(url, params=params)
        data = response.json()

        if "topalbums" not in data:
            print("Error getting albums:", data)
            break

        batch = data["topalbums"]["album"]

        if not batch:
            break

        albums.extend(batch)

        total_pages = int(data["topalbums"]["@attr"]["totalPages"])

        print(f"Albums: page {page}/{total_pages}")

        if page >= total_pages:
            break

        page += 1

    return albums


def get_top_tracks():
    """Get all tracks from your Last.fm library with automatic retries."""

    tracks = []
    page = 1

    MAX_RETRIES = 5

    while True:

        url = "https://ws.audioscrobbler.com/2.0/"

        params = {
            "method": "user.gettoptracks",
            "user": LASTFM_USERNAME,
            "api_key": LASTFM_API_KEY,
            "format": "json",
            "limit": 200,
            "page": page,
            "period": "overall"
        }

        # Try this page multiple times
        for attempt in range(1, MAX_RETRIES + 1):

            try:

                response = requests.get(
                    url,
                    params=params,
                    timeout=30
                )

                data = response.json()

                # Check whether Last.fm returned an error
                if "error" in data:

                    print(
                        f"Tracks page {page}: "
                        f"Last.fm error (attempt "
                        f"{attempt}/{MAX_RETRIES}): "
                        f"{data}"
                    )

                    if attempt < MAX_RETRIES:
                        wait_time = attempt * 5

                        print(
                            f"Retrying in {wait_time} seconds..."
                        )

                        time.sleep(wait_time)

                        continue

                    else:
                        print(
                            f"Tracks page {page} failed after "
                            f"{MAX_RETRIES} attempts."
                        )

                        return None

                # Check that the expected data exists
                if "toptracks" not in data:

                    print(
                        f"Tracks page {page}: unexpected response "
                        f"(attempt {attempt}/{MAX_RETRIES})"
                    )

                    if attempt < MAX_RETRIES:
                        wait_time = attempt * 5

                        print(
                            f"Retrying in {wait_time} seconds..."
                        )

                        time.sleep(wait_time)

                        continue

                    else:
                        print(
                            f"Tracks page {page} failed after "
                            f"{MAX_RETRIES} attempts."
                        )

                        return None

                # Success!
                batch = data["toptracks"]["track"]

                if not batch:
                    return tracks

                tracks.extend(batch)

                total_pages = int(
                    data["toptracks"]["@attr"]["totalPages"]
                )

                print(
                    f"Tracks: page {page}/{total_pages}"
                )

                # Move to next page
                if page >= total_pages:
                    return tracks

                page += 1

                # Leave the retry loop
                break

            except requests.RequestException as error:

                print(
                    f"Tracks page {page}: connection error "
                    f"(attempt {attempt}/{MAX_RETRIES}): {error}"
                )

                if attempt < MAX_RETRIES:

                    wait_time = attempt * 5

                    print(
                        f"Retrying in {wait_time} seconds..."
                    )

                    time.sleep(wait_time)

                else:

                    print(
                        f"Tracks page {page} failed after "
                        f"{MAX_RETRIES} attempts."
                    )

                    return None

            except ValueError as error:

                print(
                    f"Tracks page {page}: invalid response "
                    f"(attempt {attempt}/{MAX_RETRIES}): {error}"
                )

                if attempt < MAX_RETRIES:

                    wait_time = attempt * 5

                    print(
                        f"Retrying in {wait_time} seconds..."
                    )

                    time.sleep(wait_time)

                else:

                    print(
                        f"Tracks page {page} failed after "
                        f"{MAX_RETRIES} attempts."
                    )

                    return None

# ============================================
# RANKING PROCESSING
# ============================================

def make_ranking(items, category):
    ranking = {}

    for position, item in enumerate(items, start=1):

        if category == "artist":
            name = item["name"]

        elif category == "album":
            name = f'{item["artist"]["name"]} - {item["name"]}'

        elif category == "track":
            name = f'{item["artist"]["name"]} - {item["name"]}'

        else:
            continue

        playcount = int(item.get("playcount", 0))

        ranking[name] = {
            "position": position,
            "scrobbles": playcount
        }

    return ranking

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

        # Only report artists/albums/tracks that moved UP
        if new_position >= old_position:
            continue

        movement = old_position - new_position

        # Find everything this item overtook
        overtaken = []

        for other_name, other_old in old.items():

            if other_name == name:
                continue

            if other_name not in new:
                continue

            other_old_position = other_old["position"]
            other_new_position = new[other_name]["position"]

            # The other item used to be ahead,
            # but is now behind
            if (
                other_old_position < old_position
                and other_new_position > new_position
            ):
                overtaken.append({
                    "name": other_name,
                    "scrobbles": new[other_name]["scrobbles"],
                    "position": other_new_position
                })

        # Sort overtaken items by their new position
        overtaken.sort(key=lambda x: x["position"])

        scrobble_change = current["scrobbles"] - old[name]["scrobbles"]

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

    messages = []

    for move in movements:

        message = (
            f"{category_names[category]}\n"
            f"🚨 **{move['name']}**\n"
            f"🎧 **{move['scrobbles']:,} scrobbles** "
            f"(+{move['scrobble_change']:,})\n"
            f"📈 **#{move['old_position']} → #{move['new_position']}** "
            f"(+{move['movement']})"
        )

        if move["overtaken"]:

            overtaken_count = len(move["overtaken"])

            if overtaken_count > 10:

                message += (
                    f"\n⬆️ **Overtook {overtaken_count} "
                    f"{category.lower()}s**"
                )

            else:

                message += "\n⬆️ **Overtook:**"

                for person in move["overtaken"]:
                    message += (
                        f"\n• #{person['position']} "
                        f"**{person['name']}** "
                        f"({person['scrobbles']:,} scrobbles)"
                    )

        messages.append(message)

    # Send each movement separately so Discord messages
    # remain readable.
    for message in messages:
        send_discord(message)


# ============================================
# DISCORD
# ============================================

def send_discord(message):

    MAX_LENGTH = 1900

    # Split the message into lines
    lines = message.split("\n")

    chunks = []
    current = ""

    for line in lines:

        # If adding this line would make the message too long
        if len(current) + len(line) + 1 > MAX_LENGTH:

            # Save the current chunk
            if current:
                chunks.append(current.rstrip())

            # If a single line is too long, split it too
            while len(line) > MAX_LENGTH:
                chunks.append(line[:MAX_LENGTH])
                line = line[MAX_LENGTH:]

            current = line + "\n"

        else:
            current += line + "\n"

    # Add remaining text
    if current.strip():
        chunks.append(current.rstrip())

    # Send all chunks
    for chunk in chunks:

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": chunk}
        )

        if response.status_code not in (200, 204):
            print(
                "Discord error:",
                response.status_code,
                response.text
            )

        # Small delay between messages
        time.sleep(0.5)

# ============================================
# LOAD / SAVE
# ============================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    with open(STATE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_state(state):

    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(
            state,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================
# MAIN
# ============================================

def check_rankings():

    old_state = load_state()
    new_state = {}

    # ----------------------------
    # ARTISTS
    # ----------------------------

    if TRACK_ARTISTS:

        print("\nGetting artists...")

        artists = get_top_artists()

        new_state["artists"] = make_ranking(
            artists,
            "artist"
        )

        if "artists" in old_state:
            compare_rankings(
                old_state["artists"],
                new_state["artists"],
                "artist"
            )

    # ----------------------------
    # ALBUMS
    # ----------------------------

    if TRACK_ALBUMS:

        print("\nGetting albums...")

        albums = get_top_albums()

        new_state["albums"] = make_ranking(
            albums,
            "album"
        )

        if "albums" in old_state:
            compare_rankings(
                old_state["albums"],
                new_state["albums"],
                "album"
            )

    # ----------------------------
    # TRACKS
    # ----------------------------

    if TRACK_TRACKS:

        print("\nGetting tracks...")

        tracks = get_top_tracks()

        if tracks is not None:

            new_state["tracks"] = make_ranking(
                tracks,
                "track"
            )

            if "tracks" in old_state:
                compare_rankings(
                    old_state["tracks"],
                    new_state["tracks"],
                    "track"
                )

        else:

            print(
                "⚠️ Track data could not be retrieved completely."
            )

            # Keep the previous ranking
            if "tracks" in old_state:
                new_state["tracks"] = old_state["tracks"]

    save_state(new_state)
    
    send_discord(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ **RANKING CHECK COMPLETE**\n"
        "🕐 Next check in **10 minutes**\n"
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

    print("Done!")

except Exception as error:

    print("ERROR:", error)
    raise
