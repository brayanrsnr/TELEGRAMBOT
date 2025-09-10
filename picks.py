# picks.py — génération des pronostics formatés SAFE / MEDIUM / RISKY

import os, requests, datetime

THEODDS_KEY = os.getenv("THEODDS_API_KEY")
REGIONS = os.getenv("ODDS_REGIONS", "eu,us,uk")
MARKETS = "h2h"
ODDS_FMT = "decimal"

# ⚽ Top ligues Europe + sports populaires
SPORT_KEYS = [
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "basketball_nba",
    "americanfootball_nfl",
    "tennis_atp_singles",
    "rugby_union_international",
]

# Seuils de classification (tu peux ajuster)
SAFE_PROB = 0.63          # ≥ 63% ≈ cote <= 1.59 (après normalisation)
SAFE_EDGE = 0.020         # +2.0% d'edge
MEDIUM_PROB_LOW = 0.55    # 55%–63%
MEDIUM_EDGE = 0.010       # +1.0% d'edge

# Répartition cible (modifie si tu veux)
TARGET_SAFE = 3
TARGET_MED = 2
TARGET_TOTAL = 6  # total minimum envoyé


def _get(url, params=None):
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()


def fetch_events_for_sport(sport_key):
    """Récupère les rencontres + cotes moyennes et calcule probas/edge."""
    if not THEODDS_KEY:
        return []
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {"apiKey": THEODDS_KEY, "regions": REGIONS, "markets": MARKETS, "oddsFormat": ODDS_FMT}
    try:
        data = _get(url, params)
    except Exception:
        return []

    out = []
    for ev in data:
        prices_by_outcome = {}
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk.get("key") != "h2h":
                    continue
                for o in mk.get("outcomes", []):
                    prices_by_outcome.setdefault(o["name"], []).append(o["price"])
        if not prices_by_outcome:
            continue

        # moyenne des cotes par issue
        avg_price = {name: sum(v) / len(v) for name, v in prices_by_outcome.items()}
        # proba implicite normalisée
        imp = {name: 1.0 / p for name, p in avg_price.items()}
        s = sum(imp.values())
        probs = {name: v / s for name, v in imp.items()}

        # favori
        pick_team, pick_prob = max(probs.items(), key=lambda x: x[1])
        pick_price = avg_price[pick_team]

        # edge simple = proba - break-even (1/price)
        edge = pick_prob - (1.0 / pick_price)

        # petit bonus domicile (foot seulement)
        home_team = ev.get("home_team")
        away_team = ev.get("away_team")
        is_home_fav = (pick_team == home_team)
        score = pick_prob * 100.0 + (edge * 100.0)
        if is_home_fav and "soccer" in sport_key:
            score += 2.0

        out.append({
            "sport": sport_key,
            "home": home_team,
            "away": away_team,
            "pick": pick_team,
            "price": pick_price,
            "prob": pick_prob,
            "edge": edge,
            "score": score,
            "commence": ev.get("commence_time", "")
        })
    return out


def fmt_ts(ts):
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d/%m %H:%M UTC")
    except Exception:
        return ""


def label_for(p):
    """Retourne ('safe'|'medium'|'risky') selon prob/edge."""
    prob = p["prob"]
    edge = p["edge"]
    if (prob >= SAFE_PROB) or (prob >= 0.60 and edge >= SAFE_EDGE):
        return "safe"
    if (MEDIUM_PROB_LOW <= prob < SAFE_PROB) or (edge >= MEDIUM_EDGE):
        return "medium"
    return "risky"


def collect_all():
    events = []
    if not THEODDS_KEY:
        return []
    for key in SPORT_KEYS:
        events += fetch_events_for_sport(key)
    # trier par score décroissant (les plus pertinents en premier)
    events.sort(key=lambda x: (x["score"], x["prob"]), reverse=True)
    return events


def build_daily_message():
    if not THEODDS_KEY:
        return ("*📊 Pronostics du jour*\n"
                "_Ajoute THEODDS_API_KEY dans Render → Environment pour activer les picks._")

    all_events = collect_all()
    if not all_events:
        return "*📊 Pronostics du jour*\n_Pas de matchs exploitables trouvés aujourd'hui._"

    # Grouper par label
    groups = {"safe": [], "medium": [], "risky": []}
    for p in all_events:
        groups[label_for(p)].append(p)

    # Sélection : priorité SAFE puis MEDIUM puis RISKY, en respectant TARGETS
    chosen = []
    chosen += groups["safe"][:TARGET_SAFE]
    chosen += groups["medium"][:TARGET_MED]
    # compléter jusqu'à TARGET_TOTAL avec le reste des meilleurs
    if len(chosen) < TARGET_TOTAL:
        pool = groups["safe"][TARGET_SAFE:] + groups["medium"][TARGET_MED:] + groups["risky"]
        pool.sort(key=lambda x: (x["score"], x["prob"]), reverse=True)
        need = max(0, TARGET_TOTAL - len(chosen))
        chosen += pool[:need]

    # Construire le message avec sections
    sections = {"safe": [], "medium": [], "risky": []}
    for p in chosen:
        prob = int(round(p["prob"] * 100))
        when = fmt_ts(p["commence"])
        vs = f"{p['home']} vs {p['away']}"
        line = (f"• *{p['pick']}* — {vs}\n"
                f"  Cote moy: {p['price']:.2f}  | Confiance≈ {prob}%"
                f"{('  | Match ' + when) if when else ''}")
        sections[label_for(p)].append(line)

    lines = []
    today = datetime.datetime.utcnow().strftime("%d %B").title()
    lines.append(f"*📊 Pronostics du jour — {today}*")
    lines.append("")

    if sections["safe"]:
        lines.append("✅ *SAFE BETS*")
        lines += sections["safe"]
        lines.append("")

    if sections["medium"]:
        lines.append("⚡ *MEDIUM BETS*")
        lines += sections["medium"]
        lines.append("")

    if sections["risky"]:
        lines.append("🎲 *RISKY BETS*")
        lines += sections["risky"]
        lines.append("")

    lines.append("—")
    lines.append("💡 *Gestion du risque:* mise 1–2% par pari. Pas de martingale.")
    return "\n".join(lines)
