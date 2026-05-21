"""主程式：scrape → diff → filter → notify。"""
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from scraper import scrape_all
from filter import is_target_game, is_target_zone
from state import load_state, save_state, diff_new_availability
from notifier import notify_tickets, notify_season_paused, notify_season_resumed

NOTIFY_STATE_PATH = Path("notify_state.json")
SEASON_STATE_PATH = Path("season_state.json")


def _load_season_paused():
    if not SEASON_STATE_PATH.exists():
        return False
    try:
        return bool(json.loads(SEASON_STATE_PATH.read_text()).get("paused", False))
    except Exception:
        return False


def _save_season_paused(paused):
    SEASON_STATE_PATH.write_text(json.dumps({
        "paused": paused,
        "updated_at": datetime.now().isoformat(),
    }))


def mark_notified():
    NOTIFY_STATE_PATH.write_text(json.dumps({"last_notify_at": datetime.now().isoformat()}))


def main():
    try:
        games = scrape_all(headless=True)
    except Exception as e:
        print(f"[main] scrape 失敗: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 賽季開關：抓不到任何場次 → 暫停（只通知一次），抓到 → 恢復（只通知一次）
    paused = _load_season_paused()
    if not games:
        if not paused:
            print("[main] 找不到任何場次，推暫停通知並進入 paused 狀態")
            notify_season_paused()
            _save_season_paused(True)
            mark_notified()
        else:
            print("[main] 仍無場次，paused 狀態，靜默跳過")
        return
    if paused:
        print(f"[main] 重新抓到 {len(games)} 場，推恢復通知並解除 paused")
        notify_season_resumed(len(games))
        _save_season_paused(False)
        mark_notified()

    # 過濾：目標場次（假日 + 主場）+ 目標區域（依站台規則）
    target_games = []
    for g in games:
        if not is_target_game(g):
            continue
        g["zones"] = [z for z in g.get("zones", []) if is_target_zone(z["name"], source=g.get("source"))]
        target_games.append(g)

    total_zones = sum(len(g["zones"]) for g in target_games)
    print(f"[main] 目標場次 {len(target_games)} 場、合計 {total_zones} 個目標區域")

    prev = load_state()
    new_events, new_state = diff_new_availability(target_games, prev)
    save_state(new_state)

    if not new_events:
        print("[main] 無新釋出餘票，靜默跳過")
        return

    new_keys = {(g.get("source"), g["date"], z["name"]) for g, z in new_events}
    print(f"[main] 推播：新釋出 {len(new_keys)} 區，列出所有可購")
    notify_tickets(target_games, new_keys)
    mark_notified()


if __name__ == "__main__":
    main()
