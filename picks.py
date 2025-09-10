import os, requests, math, datetime

THEODDS_KEY = os.getenv("THEODDS_API_KEY") or os.getenv("ODDS_API_KEY")
REGIONS = os.getenv("ODDS_REGIONS", "eu,us,uk")     # marchés consultés
MARKETS = "h2h"                                     # 1X2 / moneyline
ODDS_FMT = "decimal"

# Liste de sports TheOddsAPI à couvrir (tu peux en ajouter/retirer)
SPORT_KEYS = [
    "soccer_epl", "soccer_france_ligue_one", "soccer_uefa_champs_league",
    "basketball_nba",
    "americanfootball_nfl",
    "tennis_atp_singles",
    "rugby_union_international"
]

def _get(url, params=None):
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_events_for_sport(sport_key):
    base = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {"apiKey": THEODDS_KEY, "regions": REGIONS, "markets": MARKETS, "oddsFormat": ODDS_FMT}
    try:
        data = _get(base, params)
    except Exception:
        return []
    events = []
    for ev in data:
        # Chaque bookmaker propose des cotes; on prend la moyenne par outcome
        outcomes = {}
        count = 0
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk.get("key") != "h2h":
                    continue
                count += 1
                for o in mk.get("outcomes", []):
                    outcomes.setdefault(o["name"], []).append(o["price"])
        if not outcomes or count == 0:
            continue
        avg = {name: sum(prices)/len(prices) for name, prices in outcomes.items()}
        # Convertir en probas implicites
        imp = {name: 1.0/price for name, price in avg.items()}
        norm = sum(imp.values())
        probs = {name: v/norm for name, v in imp.items()}

        # On prend le favori (plus haute proba), c'est notre pick baseline
        best_team, best_prob = max(probs.items(), key=lambda x: x[1])
        best_price = avg[best_team]
        # "Edge" très simple: prob - break-even (=1/price)
        edge = best_prob - (1.0/best_price)

        events.append({
            "sport": sport_key,
            "commence": ev.get("commence_time", ""),
            "home": ev.get("home_team"),
            "away": ev.get("away_team"),
            "pick": best_team,
            "price": best_price,
            "prob": best_prob,
            "edge": edge
        })
    return events

def pick_top_n(n=6):
    all_events = []
    if not THEODDS_KEY:
        # Pas de clé -> message placeholder
        return [{"sport":"INFO","pick":"Ajoute THEODDS_API_KEY dans Railway Variables","price":0,"prob":0.0,"edge":0.0,
                 "home":"","away":"","commence":""} for _ in range(n)]
    for key in SPORT_KEYS:
        all_events += fetch_events_for_sport(key)
    # Trier par score "edge" + prob (favoris plus clairs d'abord)
    all_events.sort(key=lambda x: (x["edge"], x["prob"]), reverse=True)
    return all_events[:n] if len(all_events) >= n else all_events

def fmt_ts(ts):
    try:
        # 2025-09-11T09:30:00Z
        dt = datetime.datetime.fromisoformat(ts.replace("Z","+00:00"))
        return dt.strftime("%d/%m %H:%M UTC")
    except Exception:
        return ""

def build_daily_message():
    picks = pick_top_n(6)
    lines = []
    lines.append("*🔥 Sélection IA – 6 pronostics du jour (18h Sydney)*")
    for i, p in enumerate(picks, 1):
        prob = int(round(p["prob"]*100)) if p["prob"] else 0
        edge = int(round(p["edge"]*10000))/100 if p["edge"] else 0.0  # en %
        vs = f"{p['home']} vs {p['away']}" if p["home"] and p["away"] else ""
        when = fmt_ts(p["commence"])
        lines.append(f"*{i}. {p['sport']}* — {vs}\n"
                     f"• Pick: *{p['pick']}*  | Cote moy: {p['price']:.2f}  | Confiance≈ {prob}%  | Edge≈ {edge}%\n"
                     f"• {('Match '+when) if when else ''}")
    lines.append("\n*Gestion du risque:* mise 1–2% par pari. Pas de martingale.")
    return "\n".join(lines)
