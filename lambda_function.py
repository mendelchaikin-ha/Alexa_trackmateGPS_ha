"""
Home Assistant Bus Tracker - Alexa Skill
Dynamically discovers TrackMate device_tracker entities from HA
and reports bus location + distance from home.
"""

import json
import urllib.request
import urllib.parse
import math
import re
import os

HA_URL = os.environ["HA_URL"]          # e.g. https://yourhome.duckdns.org
HA_TOKEN = os.environ["HA_TOKEN"]      # Long-lived access token
TRACKMATE_DOMAIN = os.environ.get("TRACKMATE_DOMAIN", "trackmate")

HA_HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json"
}


# ---------------------------------------------------------------------------
# Alexa entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    request_type = event["request"]["type"]

    if request_type == "LaunchRequest":
        return speak("Ask me where a bus is. For example, say where is bus 2.")

    if request_type == "IntentRequest":
        intent = event["request"]["intent"]["name"]

        if intent == "WhereIsBusIntent":
            return handle_bus_location(event)
        if intent in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            return speak("Goodbye!")
        if intent == "AMAZON.HelpIntent":
            return speak("Ask me where a bus is. For example, say where is bus 2.")

    return speak("I didn't catch that. Try asking where is bus 2.")


# ---------------------------------------------------------------------------
# Intent handler
# ---------------------------------------------------------------------------

def handle_bus_location(event):
    slots = event["request"]["intent"].get("slots", {})
    bus_input = slots.get("busNumber", {}).get("value", "").lower().strip()

    if not bus_input:
        return speak("Which bus would you like? For example, say where is bus 2.")

    bus_number = normalize_number(bus_input)
    if not bus_number:
        return speak("I didn't catch which bus number you said.")

    entity_id = find_bus_entity(bus_number)
    if not entity_id:
        return speak(f"I couldn't find bus {bus_number} in your TrackMate integration.")

    bus_data = ha_get(f"states/{entity_id}")
    if not bus_data:
        return speak("I couldn't reach Home Assistant.")

    state = bus_data.get("state", "unknown")
    attrs = bus_data.get("attributes", {})
    lat = attrs.get("latitude")
    lon = attrs.get("longitude")

    # HA already resolved to a named zone (e.g. "home", "school")
    if state not in ("not_home", "unknown", None):
        return speak(f"Bus {bus_number} is at {state}.")

    if not lat or not lon:
        return speak(f"Bus {bus_number} is being tracked but has no location right now.")

    # Fetch home coordinates
    home_data = ha_get("states/zone.home")
    home_lat = home_data["attributes"]["latitude"] if home_data else None
    home_lon = home_data["attributes"]["longitude"] if home_data else None

    address = reverse_geocode(lat, lon)

    distance_str = ""
    if home_lat and home_lon:
        miles = haversine_miles(lat, lon, home_lat, home_lon)
        if miles < 0.1:
            distance_str = "less than a tenth of a mile from home"
        elif miles < 1:
            distance_str = f"{round(miles * 10) / 10} miles from home"
        else:
            distance_str = f"{round(miles, 1)} miles from home"

    if address and distance_str:
        return speak(f"Bus {bus_number} is near {address}, about {distance_str}.")
    elif address:
        return speak(f"Bus {bus_number} is near {address}.")
    elif distance_str:
        return speak(f"Bus {bus_number} is {distance_str}, but I couldn't get a street address.")
    else:
        return speak(f"Bus {bus_number} is at {round(lat, 4)}, {round(lon, 4)}.")


# ---------------------------------------------------------------------------
# Entity discovery
# ---------------------------------------------------------------------------

def find_bus_entity(bus_number):
    """
    Query HA entity registry to find TrackMate device_trackers,
    then match by bus number in entity_id or friendly_name.
    Falls back to pattern-matching all device_tracker states.
    """
    registry = ha_post("config/entity_registry/list", {})

    if registry:
        trackmate_entities = [
            e["entity_id"] for e in registry
            if e.get("platform") == TRACKMATE_DOMAIN
            and e["entity_id"].startswith("device_tracker.")
        ]
    else:
        # Fallback: filter all states by domain keyword in entity_id
        all_states = ha_get("states") or []
        trackmate_entities = [
            s["entity_id"] for s in all_states
            if s["entity_id"].startswith("device_tracker.")
            and TRACKMATE_DOMAIN in s["entity_id"]
        ]

    pattern = re.compile(rf'\b{re.escape(bus_number)}\b', re.IGNORECASE)

    for entity_id in trackmate_entities:
        if pattern.search(entity_id):
            return entity_id
        # Also check friendly_name
        state_data = ha_get(f"states/{entity_id}")
        if state_data:
            friendly = state_data.get("attributes", {}).get("friendly_name", "")
            if pattern.search(friendly):
                return entity_id

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_number(text):
    """Convert spoken number words to digit strings."""
    word_map = {
        "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
        "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
        "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
        "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
        "nineteen": "19", "twenty": "20",
    }
    text = text.strip().lower()
    if text.isdigit():
        return text
    return word_map.get(text)


def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def reverse_geocode(lat, lon):
    params = urllib.parse.urlencode({
        "lat": lat, "lon": lon,
        "format": "json", "zoom": 16, "addressdetails": 1
    })
    url = f"https://nominatim.openstreetmap.org/reverse?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "HomeAssistantAlexaSkill/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        addr = data.get("address", {})
        parts = []
        if addr.get("road"):
            parts.append(f"{addr.get('house_number', '')} {addr['road']}".strip())
        if addr.get("suburb") or addr.get("neighbourhood"):
            parts.append(addr.get("suburb") or addr.get("neighbourhood"))
        if addr.get("city") or addr.get("town") or addr.get("village"):
            parts.append(addr.get("city") or addr.get("town") or addr.get("village"))
        return ", ".join(parts) if parts else data.get("display_name", "")
    except Exception:
        return None


def ha_get(path):
    url = f"{HA_URL}/api/{path}"
    req = urllib.request.Request(url, headers=HA_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def ha_post(path, body):
    url = f"{HA_URL}/api/{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=HA_HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def speak(text, end_session=True):
    return {
        "version": "1.0",
        "response": {
            "outputSpeech": {"type": "PlainText", "text": text},
            "shouldEndSession": end_session
        }
    }
