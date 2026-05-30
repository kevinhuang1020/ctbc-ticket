"""過濾邏輯：假日（週六日 + 國定假日）+ 指定區域 + 主場場館。"""
import os
from datetime import datetime, date
import holidays

DEFAULT_HOME_VENUES = ["洲際", "大巨蛋", "新莊"]  # substring 比對
DEFAULT_WEEKDAYS = [5, 6]  # 週六、週日
DEFAULT_ZONE_PREFIXES = ["C", "D", "E", "F"]  # 中信（洲際）目標英文字母區
# 大巨蛋以數字命名（108 區、109 區 ...），單獨用 substring 比對
DEFAULT_DOME_ZONE_NUMBERS = ["108", "109", "110", "111", "112", "113", "114", "115", "116", "117", "118"]
# 富邦（新莊）目標：A3~A6、B3~B6 區（本壘正後方），含「熱力區」變體
DEFAULT_GUARDIANS_ZONE_PATTERN = r"^[AB][3-6](區|熱力區)$"

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


def is_target_zone(zone_name, source=None):
    """source = 'brothers' / 'guardians' / None（不知道時用全規則）。"""
    import re
    # 排除輪椅席（任何站台）
    if "輪椅" in zone_name:
        return False

    # 富邦站：新莊 → A1~A7 / B1~B7（含熱力區）；大巨蛋 → 108/109/110/116/117/118 各子分區
    if source == "guardians":
        pat = os.getenv("GUARDIANS_ZONE_PATTERN", DEFAULT_GUARDIANS_ZONE_PATTERN)
        if re.match(pat, zone_name):
            return True
        dome_nums = _env_list("DOME_ZONE_NUMBERS", DEFAULT_DOME_ZONE_NUMBERS)
        if any(re.search(rf"(?<!\d){n}(?!\d)", zone_name) for n in dome_nums):
            return True
        return False

    # 中信站 or 未指定來源：洲際英文字母區 + 大巨蛋數字區
    prefixes = _env_list("ZONE_PREFIXES", DEFAULT_ZONE_PREFIXES)
    dome_nums = _env_list("DOME_ZONE_NUMBERS", DEFAULT_DOME_ZONE_NUMBERS)
    # 大巨蛋數字區（108/109/110/116/117/118 ...）
    if any(re.search(rf"(?<!\d){n}(?!\d)", zone_name) for n in dome_nums):
        return True
    # 排除上層（僅針對洲際的英文字母區）
    if "上層" in zone_name:
        return False
    letters = re.findall(r"[A-Z]", zone_name.upper())
    return any(L in prefixes for L in letters)


def filter_events(games):
    """回傳 [(game, zone), ...] — 已過濾過、且有票的組合。"""
    out = []
    for g in games:
        if not is_target_game(g):
            continue
        for z in g.get("zones", []):
            if not is_target_zone(z["name"], source=g.get("source")):
                continue
            if z.get("available", 0) <= 0:
                continue
            out.append((g, z))
    return out
