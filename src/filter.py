"""過濾邏輯：假日（週六日 + 國定假日）+ 指定區域 + 主場場館。"""
import os
from datetime import datetime, date
import holidays

DEFAULT_HOME_VENUES = ["洲際", "大巨蛋"]  # substring 比對，含「臺中洲際」「臺北大巨蛋」
DEFAULT_WEEKDAYS = [5, 6]  # 週六、週日
DEFAULT_ZONE_PREFIXES = ["C", "D", "E", "F"]

# 台灣國定假日（含補假），library 會自動處理春節/補假等規則
_TW_HOLIDAYS = holidays.Taiwan(years=range(date.today().year, date.today().year + 2))


def _env_list(key, default):
    v = os.getenv(key)
    if not v:
        return default
    return [x.strip() for x in v.split(",") if x.strip()]


def _is_holiday(date_str):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return d in _TW_HOLIDAYS


def is_target_game(game):
    venues = _env_list("VENUES", DEFAULT_HOME_VENUES)
    weekdays = [int(x) for x in _env_list("WEEKDAYS", [str(d) for d in DEFAULT_WEEKDAYS])]
    if not any(v in game.get("venue", "") for v in venues):
        return False
    if game.get("weekday_idx") in weekdays:
        return True
    if _is_holiday(game.get("date", "")):
        return True
    return False


def is_target_zone(zone_name):
    prefixes = _env_list("ZONE_PREFIXES", DEFAULT_ZONE_PREFIXES)
    # 排除上層
    if "上層" in zone_name:
        return False
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
