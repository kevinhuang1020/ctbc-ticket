"""過濾邏輯：假日場次 + 指定區域 + 主場場館。"""
import os

DEFAULT_HOME_VENUES = ["洲際", "大巨蛋"]  # substring 比對，含「臺中洲際」「臺北大巨蛋」
DEFAULT_WEEKDAYS = [5, 6]  # 週六、週日
DEFAULT_ZONE_PREFIXES = ["C", "D", "E", "F"]


def _env_list(key, default):
    v = os.getenv(key)
    if not v:
        return default
    return [x.strip() for x in v.split(",") if x.strip()]


def is_target_game(game):
    venues = _env_list("VENUES", DEFAULT_HOME_VENUES)
    weekdays = [int(x) for x in _env_list("WEEKDAYS", [str(d) for d in DEFAULT_WEEKDAYS])]
    if game.get("weekday_idx") not in weekdays:
        return False
    if not any(v in game.get("venue", "") for v in venues):
        return False
    return True


def is_target_zone(zone_name):
    prefixes = _env_list("ZONE_PREFIXES", DEFAULT_ZONE_PREFIXES)
    # 區域名稱可能是「內野南C區下層」「外野F區」等 — 抓出英文字母再比對
    import re
    letters = re.findall(r"[A-Z]", zone_name.upper())
    return any(L in prefixes for L in letters)


def filter_events(games):
    """回傳 [(game, zone), ...] — 已過濾過、且有票的組合。"""
    out = []
    for g in games:
        if not is_target_game(g):
            continue
        for z in g.get("zones", []):
            if not is_target_zone(z["name"]):
                continue
            if z.get("available", 0) <= 0:
                continue
            out.append((g, z))
    return out
