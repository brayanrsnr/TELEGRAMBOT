import os, requests, datetime

THEODDS_KEY = os.getenv("THEODDS_API_KEY")
REGIONS = os.getenv("ODDS_REGIONS", "eu,us,uk")
MARKETS = "h2h"
ODDS_FMT = "decimal"

# Ligues & sports
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

# Seuils / objectifs
SAFE_PROB = 0.63          # proba normalisée
SAFE_EDGE = 0.020         # +2.0% d'edge
MEDIUM_PROB_LOW = 0.55
MEDIUM_EDGE = 0.010

TARGET_SAFE = 3
TARGET_MED = 2
TARGET_TOTAL = 6

# Unités de mise (bankroll % indicatif)
UNITS = {"safe": "1.0u", "medium": "0.7u", "risky": "0.4u"}

def _get(url, params=None):
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def _fmt_ts(ts):
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d/%m %H:%M UTC")
    except Exception:
        return ""

def _label(p):
    prob = p["prob"]; edge = p["edge"]
    if (prob >= SAFE_PROB) or (prob >= 0.60 and edge >= SAFE_EDGE):
        return "safe"
    if (MEDIUM_PROB_LOW <= prob < SAFE_PROB) or (edge >= MEDIUM_EDGE):
        return "medium"
    return "risky"

def _badge(label):
    return {"safe": "✅ SAFE", "medium": "⚡ MEDIUM", "risky": "🎲 RISKY"}[label]

def fetch_events_for_sport(sport_key):
    if not THEODDS_KEY: return []
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {"apiKey": THEODDS_KEY, "regions": REGIONS, "markets": MARKETS, "oddsFormat": ODDS_FMT}
    try:
        data = _get(url, params)
    except Exception:
        return []

    out = []
    for ev in data:
        # moyenne des cotes
        prices = {}
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk.get("key") != "h2h": continue
                for o in mk.get("outcomes", []):
                    prices.setdefault(o["name"], []).append(o["price"])
        if not prices: continue
        avg = {k: sum(v)/len(v) for k,v in prices.items()}

        # proba implicite normalisée
        imp = {k: 1.0/p for k,p in avg.items()}
        s = sum(imp.values()); probs = {k: v/s for k,v in imp.items()}

        pick, prob = max(probs.items(), key=lambda x: x[1])
        price = avg[pick]
        edge = prob - (1.0/price)

        home, away = ev.get("home_team"), ev.get("away_team")
        is_home = (pick == home)
        score = prob*100 + edge*100 + (2.0 if ("soccer" in sport_key and is_home) else 0.0)

        out.append({
            "sport": sport_key,
            "home": home, "away": away,
            "pick": pick, "price": price,
            "prob": prob, "edge": edge,
            "score": score,
            "commence": ev.get("commence_time","")
        })
    return out

def _collect_all():
    events = []
    for k in SPORT_KEYS:
        events += fetch_events_for_sport(k)
    events.sort(key=lambda x: (x["score"], x["prob"]), reverse=True)
    return events

def _select_vip():
    """Retourne (chosen, stats) où chosen est la liste finale ordonnée."""
    all_events = _collect_all()
    groups = {"safe": [], "medium": [], "risky": []}
    for p in all_events:
        groups[_label(p)].append(p)

    chosen = []
    chosen += groups["safe"][:TARGET_SAFE]
    chosen += groups["medium"][:TARGET_MED]
    if len(chosen) < TARGET_TOTAL:
        pool = groups["safe"][TARGET_SAFE:] + groups["medium"][TARGET_MED:] + groups["risky"]
        pool.sort(key=lambda x: (x["score"], x["prob"]), reverse=True)
        chosen += pool[:(TARGET_TOTAL - len(chosen))]

    stats = {
        "scanned": len(all_events),
        "safe": len(groups["safe"]),
        "medium": len(groups["medium"]),
        "risky": len(groups["risky"]),
        "selected": len(chosen),
    }
    return chosen, stats

def build_daily_message():
    if not THEODDS_KEY:
        return ("*📣 Configuration requise*\n"
                "_Ajoute THEODDS_API_KEY dans Render → Environment pour activer les picks._")

    picks, stats = _select_vip()
    if not picks:
        return "*📊 VIP Picks*\n_Aucun match exploitable trouvé aujourd’hui._"

    # Titre VIP
    today = datetime.datetime.utcnow().strftime("%d %b %Y")
    lines = []
    lines.append(f"*👑 VIP Picks — {today}*")
    lines.append("_Modèle : proba implicite multi-books + edge + bonus domicile (foot)_")
    lines.append("")

    # Sections
    for p in picks:
        label = _label(p)
        badge = _badge(label)
        units = UNITS[label]
        prob = int(round(p["prob"]*100))
        edge = int(round(p["edge"]*1000))/10  # ex: 2.3%
        when = _fmt_ts(p["commence"])
        vs = f"{p['home']} vs {p['away']}"
        lines.append(
            f"{badge} · *{units}*\n"
            f"• *{p['pick']}* — {vs}\n"
            f"  Cote: *{p['price']:.2f}* | Confiance≈ *{prob}%* | Edge≈ *{edge}%*"
            f"{(' | ' + when) if when else ''}"
        )
        lines.append("")

    # Footer
    lines.append("—")
    lines.append("💼 *Gestion* : 1–2% bankroll par pari (unités ci-dessus).")
    lines.append("📌 *Avertissement* : les paris comportent des risques. Joue responsable.")
    return "\n".join(lines)

def build_status():
    """Petit résumé VIP pour /status."""
    if not THEODDS_KEY:
        return "*Status* : clé THEODDS_API_KEY manquante."
    _, st = _select_vip()
    return (f"*Status VIP*\n"
            f"Scannés: *{st['scanned']}* | Sélectionnés: *{st['selected']}*\n"
            f"Répartition: ✅ {st['safe']} · ⚡ {st['medium']} · 🎲 {st['risky']}")
