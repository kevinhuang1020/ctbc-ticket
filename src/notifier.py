"""LINE Messaging API 推播 — 移植自 taiwan-stock-picker。"""
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
USER_ID = os.getenv("LINE_USER_ID")
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_MAX_CHARS = 4900


def _split_chunks(text, size=LINE_MAX_CHARS):
    if len(text) <= size:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:size])
        text = text[size:]
    return chunks


def send_line_message(text, quiet=False):
    if not TOKEN or not USER_ID:
        print("[notifier] 未設定 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_USER_ID，跳過推播")
        return False
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {TOKEN}",
    }
    ok = True
    for chunk in _split_chunks(text):
        payload = {"to": USER_ID, "messages": [{"type": "text", "text": chunk}]}
        try:
            r = requests.post(LINE_PUSH_URL, headers=headers, json=payload, timeout=10)
            if r.status_code != 200:
                print(f"[notifier] 推播失敗 {r.status_code}: {r.text}")
                ok = False
            elif not quiet:
                print("[notifier] 推播成功")
        except Exception as e:
            print(f"[notifier] 推播異常: {e}")
            ok = False
    return ok


def _fmt_avail(n):
    if n == -1:
        return "熱賣中"
    if isinstance(n, int) and n > 0:
        return f"剩 {n} 張"
    return ""


def notify_tickets(events):
    """events: list of dict {date, weekday, opponent, venue, zone, price, available, url}"""
    if not events:
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"🎫 中信兄弟餘票通知  {now}", ""]
    by_game = {}
    for e in events:
        key = (e["date"], e["weekday"], e["opponent"], e["venue"])
        by_game.setdefault(key, []).append(e)
    for (date, weekday, opp, venue), zs in by_game.items():
        lines.append(f"📅 {date}({weekday}) 中信 vs {opp} @ {venue}")
        for z in zs:
            price = f"  ${z['price']}" if z.get("price") else ""
            avail = _fmt_avail(z.get("available", -1))
            avail_s = f"  [{avail}]" if avail else ""
            lines.append(f"   • {z['zone']}{price}{avail_s}")
        lines.append(f"   🔗 {zs[0].get('game_url', '')}")
        lines.append("")
    lines.append("⚠️ 請手動前往購票，本程式不會自動下單")
    return send_line_message("\n".join(lines))


if __name__ == "__main__":
    notify_tickets([{
        "date": "2026-05-03", "weekday": "日", "opponent": "樂天",
        "venue": "洲際棒球場", "zone": "內野南C區下層", "price": 500,
        "game_url": "https://tix.ctbcsports.com/BROTHERS/UTK0205_?PERFORMANCE_ID=TEST",
    }])
