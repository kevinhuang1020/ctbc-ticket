"""主程式：scrape → diff → filter → notify。"""
import json
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from scraper import scrape_all
from filter import is_target_game, is_target_zone
from state import load_state, save_state, diff_new_availability
from notifier import notify_tickets, notify_empty

EMPTY_NOTIFY_PATH = Path("empty_notify.json")
EMPTY_NOTIFY_INTERVAL = timedelta(hours=8)


def should_notify_empty():
    if not EMPTY_NOTIFY_PATH.exists():
        return True
    try:
        last = datetime.fromisoformat(json.loads(EMPTY_NOTIFY_PATH.read_text())["last_empty_at"])
    except Exception:
        return True
    return datetime.now() - last >= EMPTY_NOTIFY_INTERVAL


def mark_empty_notified():
    EMPTY_NOTIFY_PATH.write_text(json.dumps({"last_empty_at": datetime.now().isoformat()}))


def main():
    try:
        games = scrape_all(headless=True)
    except Exception as e:
        print(f"[main] scrape 失敗: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 過濾：目標場次（假日 + 主場）+ 目標區域（C/D/E/F）
    target_games = []
    for g in games:
        if not is_target_game(g):
            continue
        g["zones"] = [z for z in g.get("zones", []) if is_target_zone(z["name"])]
        target_games.append(g)

    total_zones = sum(len(g["zones"]) for g in target_games)
    print(f"[main] 目標場次 {len(target_games)} 場、合計 {total_zones} 個目標區域")

    prev = load_state()
    new_events, new_state = diff_new_availability(target_games, prev)
    save_state(new_state)

    if not new_events:
        # 檢查是不是「全部售完」狀態 — 若是且距上次通知 ≥ 8h，推一次心跳
        any_available = any(
            z.get("available", 0) != 0
            for g in target_games
            for z in g.get("zones", [])
        )
        if not any_available and total_zones > 0:
            if should_notify_empty():
                print(f"[main] 全部售完且超過 8h，推空狀態提醒")
                notify_empty(len(target_games), total_zones)
                mark_empty_notified()
            else:
                print("[main] 全部售完但 8h 內已通知過，跳過")
        else:
            print("[main] 無新釋出餘票，不通知")
        return

    payload = []
    for g, z in new_events:
        payload.append({
            "date": g["date"],
            "weekday": g["weekday"],
            "opponent": g["opponent"] or "?",
            "venue": g["venue"] or "?",
            "zone": z["name"],
            "price": z.get("price"),
            "available": z.get("available", -1),
            "game_url": g["schedule_url"],
        })
    print(f"[main] 推播 {len(payload)} 筆新餘票")
    notify_tickets(payload)


if __name__ == "__main__":
    main()
