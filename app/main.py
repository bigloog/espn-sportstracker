import time
import yaml
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # ✅ CORS import
from fastapi.responses import JSONResponse

app = FastAPI()

# ✅ CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to your frontend origin for tighter control if desired
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load config.yaml on startup
CONFIG_PATH = "config.yaml"
with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

# Simple in-memory cache: {key: (timestamp, data)}
cache = {}
CACHE_EXPIRATION = 60 * 60  # 1 hour cache expiry


def fetch_team_data(sport_slug: str, league_slug: str, team_id: int):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_slug}/{league_slug}/teams/{team_id}"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching ESPN data: {e}")


def get_cached_team_data(sport_slug: str, league_slug: str, team_slug: str, team_id: int):
    key = f"{league_slug}:{team_slug}"
    now = time.time()
    if key in cache:
        ts, data = cache[key]
        if now - ts < CACHE_EXPIRATION:
            return data

    data = fetch_team_data(sport_slug, league_slug, team_id)
    cache[key] = (now, data)
    return data


def find_sport_slug(league_slug: str):
    for league in config.get("leagues", []):
        if league.get("league") == league_slug:
            # Use sport_path if present, else fallback to sport
            return league.get("sport_path") or league.get("sport")
    return None


@app.get("/api/espn/team/{team_slug}/{league_slug}")
def api_team(team_slug: str, league_slug: str):
    for team_key, team_info in config.get("teams", {}).items():
        if team_info.get("espn_slug") == team_slug and team_info.get("league") == league_slug:
            team_id = team_info.get("espn_id")
            if not team_id:
                raise HTTPException(status_code=404, detail="Team ESPN ID not found in config")

            sport_slug = find_sport_slug(league_slug)
            if not sport_slug:
                raise HTTPException(status_code=404, detail="Sport slug not found in config")

            return get_cached_team_data(sport_slug, league_slug, team_slug, team_id)

    raise HTTPException(status_code=404, detail="Team or league not found in config")


@app.get("/api/espn/team/{team_slug}")
def api_team_no_league(team_slug: str):
    for team_key, team_info in config.get("teams", {}).items():
        if team_info.get("espn_slug") == team_slug:
            team_id = team_info.get("espn_id")
            league_slug = team_info.get("league")
            if not team_id or not league_slug:
                raise HTTPException(status_code=404, detail="Team ESPN ID or league not found in config")

            sport_slug = find_sport_slug(league_slug)
            if not sport_slug:
                raise HTTPException(status_code=404, detail="Sport slug not found in config")

            return get_cached_team_data(sport_slug, league_slug, team_slug, team_id)

    raise HTTPException(status_code=404, detail="Team not found in config")


@app.get("/api/espn/fixtures/{team_slug}/{league_slug}")
def api_fixtures(team_slug: str, league_slug: str):
    for team_key, team_info in config.get("teams", {}).items():
        if team_info.get("espn_slug") == team_slug and team_info.get("league") == league_slug:
            team_id = team_info.get("espn_id")
            if not team_id:
                raise HTTPException(status_code=404, detail="Team ESPN ID not found in config")

            sport_slug = find_sport_slug(league_slug)
            if not sport_slug:
                raise HTTPException(status_code=404, detail="Sport slug not found in config")

            data = get_cached_team_data(sport_slug, league_slug, team_slug, team_id)

            fixtures = data.get("team", {}).get("nextEvent", [])

            return {"fixtures": fixtures}

    raise HTTPException(status_code=404, detail="Team or league not found in config")


@app.get("/api/teams")
def get_all_teams():
    results = []
    for team_key, team_info in config.get("teams", {}).items():
        sport_slug = find_sport_slug(team_info.get("league"))
        if not sport_slug:
            continue
        try:
            team_data = get_cached_team_data(
                sport_slug,
                team_info.get("league"),
                team_info.get("espn_slug"),
                team_info.get("espn_id"),
            )
            # ESPN typically returns logos in a list under 'team' -> 'logos'
            logos = team_data.get("team", {}).get("logos", [])
            logo_url = logos[0].get("href") if logos else None

            results.append({
                "name": team_info.get("name"),
                "league": team_info.get("league"),
                "espn_slug": team_info.get("espn_slug"),
                "logo": logo_url,
            })
        except Exception:
            continue
    return JSONResponse(content=results)
