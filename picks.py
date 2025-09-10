import os, requests, datetime

THEODDS_KEY = os.getenv("THEODDS_API_KEY")
FD_KEY = os.getenv("FD_API_KEY")  # clé Football-Data
REGIONS = os.getenv("ODDS_REGIONS", "eu,us,uk")
MARKETS = "h2h"
ODDS_FMT = "decimal"

SPORT_KEYS = [
    "soccer_epl", "soccer_france_ligue_one", "soccer_uefa_champs_league",
    "basketball_nba",
    "americanfootball_nfl",
    "tennis_atp_singles",
    "rugby_union_international"
]

def _get(url, headers=None, params=None):
    r = requests.get(url, headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_events_for_sport(sport_key):
    if not THEODDS_KEY:
        return []
    base = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {"apiKey": THEODDS_KEY, "regions": REGIONS, "markets": MARKETS, "oddsFormat": ODDS_FMT}
    try:
        data = _get(base, params=params)
    except Exception:
        return []
    events = []
    for ev in data:
        outcomes = {}
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk.get("key") != "h2h":
                    continue
                for o in mk.get("outcomes", []):
                    outcomes.setdefault(o["name"], []).append(o["price"])
        if not outcomes:
            continue
        avg = {name: sum(prices)/len(prices) for name, prices in outcomes.items()}
        fav = min(avg, key=avg.get)
        events.append({
            "sport": sport_key,
            "home": ev.get("home_team"),
            "away": ev.get("away_team"),
            "fav": fav,
            "price": avg[fav],
            "commence": ev.get("commence_time")
        })
    return events

def fetch_team_form(team):
    """Analyse forme sur Football-Data (5 derniers matchs)"""
    if not FD_KEY:
        return None
    try:
        url = f"https://api.football-data.org/v4/teams/{team}/matches?status=FINISHED&limit=5"
        headers = {"X-Auth-Token": FD_KEY}
        matches = _get(url, headers=headers).get("matches", [])
        if not matches:
            return None
        pts = 0
        for m in matches:
            if m["score"]["winner"] == "HOME_TEAM" and m["homeTeam"]["id"] == team:
                pts += 3
            elif m["score"]["winner"] == "AWAY_TEAM" and m["awayTeam"]["id"] == team:
                pts += 3
            elif m["score"]["winner"] == "DRAW":
                pts += 1
        return round(pts / (len(matches)*3), 2)  # ratio 0-1
    except Exception:
        return None

def build_daily_message():
    lines = []
    lines.append("*🔥 Sélection IA – Pronostics du jour (18h Sydney)*")
    picks = []
    for sport in SPORT_KEYS:
        picks += fetch_events_for_sport(sport)
    top = picks[:6] if len(picks) >= 6 else picks

    for i, p in enumerate(top, 1):
        form_info = ""
        if "soccer" in p["sport"] and FD_KEY:
            form_val = fetch_team_form(p["fav"])
            if form_val is not None:
                form_info = f" | Forme={int(form_val*100)}%"
        vs = f"{p['home']} vs {p['away']}"
        when = p["commence"].replace("T", " ").replace("Z", " UTC")
        lines.append(f"*{i}. {p['sport']}* — {vs}\n"
                     f"• Pick: *{p['fav']}* | Cote≈{p['price']:.2f}{form_info}\n"
                     f"• Match: {when}")
    lines.append("\n*Gestion du risque:* mise 1–2% par pari. Pas de martingale.")
    return "\n".join(lines)
