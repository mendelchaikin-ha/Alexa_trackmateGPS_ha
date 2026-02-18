# Home Assistant Bus Tracker — Alexa Skill

Ask Alexa where any of your school buses are using your Home Assistant TrackMate GPS integration.

**Example:**
> "Alexa, ask home assistant where is bus 2"
> → "Bus 2 is near 45 Elm Street, Springfield, about 1.3 miles from home."

---

## Prerequisites

- [Alexa Developer account](https://developer.amazon.com)
- [AWS account](https://aws.amazon.com) (free tier is fine)
- [ASK CLI](https://developer.amazon.com/en-US/docs/alexa/smapi/quick-start-alexa-skills-kit-command-line-interface.html) installed (`npm install -g ask-cli`)
- Home Assistant accessible externally via HTTPS (e.g. DuckDNS)
- TrackMate integration set up in Home Assistant

---

## Setup

### 1. Get your Home Assistant Long-Lived Access Token

1. In HA, go to your **Profile** (bottom left)
2. Scroll to **Long-Lived Access Tokens** → Create token
3. Copy it — you'll need it for Lambda

### 2. Find your TrackMate integration domain name

In HA Developer Tools → Template, run:
```
{{ integration_entities('trackmate') }}
```
If that returns empty, try `trackmate_gps`. Note the domain name.

### 3. Deploy with ASK CLI

```bash
# Clone this repo
git clone https://github.com/YOUR_USERNAME/alexa-ha-bus-skill.git
cd alexa-ha-bus-skill

# Configure ASK CLI (links your Amazon developer account)
ask configure

# Deploy skill + Lambda
ask deploy
```

ASK CLI will:
- Create the Alexa skill in your developer console
- Create a Lambda function in AWS `us-east-1`
- Link them together automatically

### 4. Set Lambda Environment Variables

After deploying, go to **AWS Console → Lambda → your function → Configuration → Environment variables** and add:

| Key | Value |
|-----|-------|
| `HA_URL` | `https://yourhome.duckdns.org` |
| `HA_TOKEN` | your long-lived token from step 1 |
| `TRACKMATE_DOMAIN` | `trackmate` (or whatever step 2 returned) |

### 5. Test

In the [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask):
1. Open your skill → **Test** tab
2. Enable testing → say: `ask home assistant where is bus 2`

Or just say it to your Echo device once testing is enabled.

---

## How It Works

```
Alexa voice → Skill (intent + slot) → Lambda → HA REST API
                                             ↓           ↓
                                     Entity registry  zone.home
                                     (finds TrackMate  (home coords)
                                      device_trackers)
                                             ↓
                                     Nominatim OSM
                                     (reverse geocode)
                                             ↓
                                     Alexa speaks result
```

1. Alexa extracts the bus number from your speech
2. Lambda queries the **HA entity registry** to find all `device_tracker` entities belonging to the TrackMate integration — no hardcoded entity IDs needed
3. Matches the bus number against entity IDs and friendly names
4. Fetches lat/lon, reverse geocodes via OpenStreetMap Nominatim (free, no API key)
5. Calculates distance from `zone.home` using the Haversine formula
6. Speaks the result

---

## Supported Utterances

- "Alexa, ask home assistant where is bus 2"
- "Alexa, ask home assistant where's bus 6"
- "Alexa, ask home assistant how far is bus 2"
- "Alexa, ask home assistant what's the location of bus 6"
- "Alexa, ask home assistant is bus 2 close"
- "Alexa, ask home assistant find bus 2"

---

## Repo Structure

```
alexa-ha-bus-skill/
├── lambda/
│   └── lambda_function.py        # All skill logic
├── skill-package/
│   ├── skill.json                # Skill manifest
│   └── interactionModels/
│       └── custom/
│           └── en-US.json        # Intents, slots, utterances
├── ask-resources.json            # ASK CLI deployment config
├── .gitignore
└── README.md
```

---

## Troubleshooting

**"I couldn't find bus X in your TrackMate integration"**
- Check that `TRACKMATE_DOMAIN` matches exactly what `{{ integration_entities('trackmate') }}` returns in HA
- Verify your bus entities are `device_tracker.*` type in HA Developer Tools → States

**"I couldn't reach Home Assistant"**
- Make sure `HA_URL` is your external HTTPS URL (not local IP)
- Confirm your HA instance is accessible from the internet
- Check your Long-Lived Access Token is still valid

**Lambda timeout**
- Default Lambda timeout is 3s — increase to **10 seconds** in Lambda Configuration → General

---

## License

MIT
