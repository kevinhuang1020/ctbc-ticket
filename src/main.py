"""主程式：scrape → diff → filter → notify。"""
import sys
import traceback

from scraper import scrape_all
from filter import is_target_game, is_target_zone
from state import load_state, save_state, diff_new_availability
from notifier import notify_tickets


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
