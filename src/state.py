"""State 管理：避免重複通知。

key   = f"{performance_id}:{zone_name}"
value = available 整數（語意見下）

available 語意：
  0   售完
  -1  熱賣中（有票但網站不顯示具體張數）
  正數 剩餘張數

通知規則：
  - 第一次跑（state 空）：不通知，只 snapshot
  - 之後：上次==0 且 這次!=0  → 從沒票變有票，通知
  - 新出現的區域（之前沒看過）：如果有票就通知（可能是新開賣）
"""
import json
import os
from pathlib import Path

STATE_PATH = Path(os.getenv("STATE_PATH", "state.json"))


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def diff_new_availability(games, prev_state):
    new_state = {}
    new_events = []
    is_first_run = not prev_state

    for g in games:
        for z in g.get("zones", []):
            key = f"{z['performance_id']}:{z['name']}"
            curr = z["available"]
            new_state[key] = curr

            if is_first_run:
                continue

            prev = prev_state.get(key)
            if prev is None:
                # 新區域 — 上架了
                if curr != 0:
                    new_events.append((g, z))
            elif prev == 0 and curr != 0:
                # 售完 → 有票（退票釋出）
                new_events.append((g, z))

    return new_events, new_state
