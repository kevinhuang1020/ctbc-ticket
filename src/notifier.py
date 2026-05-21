"""Telegram Bot API 推播。"""
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TG_API_BASE = "https://api.telegram.org"
TG_MAX_CHARS = 4000  # Telegram 上限 4096 字元（每字算 1，無 UTF-16 倍率），留點餘裕


def _split_chunks(text, size=TG_MAX_CHARS):
    """按行切，每段不超過 size 字。"""
    if len(text) <= size:
        return [text]
    chunks = []
    buf = []
    buf_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1
        if line_len > size:
            if buf:
                chunks.append("\n".join(buf))
                buf, buf_len = [], 0
            s = line
            while s:
                chunks.append(s[:size])
                s = s[size:]
            continue
        if buf_len + line_len > size:
            chunks.append("\n".join(buf))
            buf, buf_len = [], 0
        buf.append(line)
        buf_len += line_len
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def send_line_message(text, quiet=False):
    """函式名保留為 send_line_message 不影響呼叫端，內部已改為 Telegram。"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[notifier] 未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，跳過推播")
        return False
    url = f"{TG_API_BASE}/bot{TG_TOKEN}/sendMessage"
    ok = True
    for chunk in _split_chunks(text):
        payload = {
            "chat_id": TG_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=10)
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


def _game_header(g):
    home = g.get("home_team") or "?"
    opp = g.get("opponent") or "?"
    venue = g.get("venue") or "?"
    return f"📅 {g['date']}({g.get('weekday','')}) {home} vs {opp} @ {venue}"


def notify_tickets(target_games, new_keys):
    """有新釋出餘票時：列出目前所有「可購買」區域，並把新釋出的區域用顯眼方式標記。

    target_games: 過濾後的場次（含 zones 與 available）。
    new_keys: set of (source, date, zone_name) 表示本次新釋出。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_count = len(new_keys)
    games_sorted = sorted(target_games, key=lambda g: (g.get("date", ""), g.get("source", "")))
    game_by_sd = {(g.get("source"), g["date"]): g for g in games_sorted}

    lines = [f"🚨🆕 有新釋出（{new_count} 區）  {now}", ""]

    # 頭部「本次新釋出」醒目區塊
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("🆕 本次新釋出區域：")
    for source, date, zone_name in sorted(new_keys):
        g = game_by_sd.get((source, date), {})
        z = next((zz for zz in g.get("zones", []) if zz["name"] == zone_name), {})
        price = f"  ${z['price']}" if z.get("price") else ""
        avail = _fmt_avail(z.get("available", -1))
        avail_s = f"  [{avail}]" if avail else ""
        home = g.get("home_team") or "?"
        opp = g.get("opponent") or "?"
        venue = g.get("venue") or "?"
        weekday = g.get("weekday", "")
        lines.append(f"  ▶ {date}({weekday}) {home} vs {opp} @ {venue}")
        lines.append(f"     👉 {zone_name}{price}{avail_s}")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("")

    # 完整可購清單
    lines.append("📋 目前所有可購買區域：")
    lines.append("")
    any_avail = False
    for g in games_sorted:
        avail_zones = [z for z in g.get("zones", []) if z.get("available", 0) != 0]
        if not avail_zones:
            continue
        any_avail = True
        lines.append(_game_header(g))
        for z in sorted(avail_zones, key=lambda x: x["name"]):
            price = f"  ${z['price']}" if z.get("price") else ""
            avail = _fmt_avail(z.get("available", -1))
            avail_s = f"  [{avail}]" if avail else ""
            is_new = (g.get("source"), g["date"], z["name"]) in new_keys
            mark = "🆕👉 " if is_new else "   • "
            tail = "  ⬅️ 新" if is_new else ""
            lines.append(f"   {mark}{z['name']}{price}{avail_s}{tail}")
        lines.append(f"   🔗 {g.get('schedule_url','')}")
        lines.append("")
    if not any_avail:
        lines.append("（目前所有目標區域皆售完）")
        lines.append("")
    lines.append("⚠️ 請手動前往購票，本程式不會自動下單")
    return send_line_message("\n".join(lines))


def notify_season_paused():
    """整季沒場次（season over）時推一次：監控暫停。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        f"⚾ 找不到任何場次，監控暫停  {now}\n\n"
        f"🛌 賽季可能已結束。下次抓到場次時會自動恢復並通知。"
    )
    return send_line_message(text)


def notify_season_resumed(games_count):
    """重新抓到場次時推一次：監控恢復。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        f"▶️ 監控恢復（找到 {games_count} 場）  {now}\n\n"
        f"🎯 已重新開始檢查目標場次餘票。"
    )
    return send_line_message(text)


def notify_empty(target_games_count, target_zones_count):
    """所有目標區域都售完時的提醒。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        f"📭 目前所有監控區域都已售完  {now}\n\n"
        f"🎯 持續監控中：{target_games_count} 場、{target_zones_count} 個 C/D/E/F 下層區\n"
        f"⏰ 8 小時後若仍無票會再次提醒\n"
        f"🔗 https://tix.ctbcsports.com/BROTHERS/UTK0102_?TYPE=4"
    )
    return send_line_message(text)


def notify_heartbeat(target_games):
    """無新釋出餘票，但距上次通知已 ≥ 8h，推一次心跳列出目前每場每區可購數量。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"💓 監控心跳（無新釋出，列出目前可購）  {now}", ""]
    games_sorted = sorted(target_games, key=lambda g: (g.get("date", ""), g.get("source", "")))
    any_avail = False
    for g in games_sorted:
        avail_zones = [z for z in g.get("zones", []) if z.get("available", 0) != 0]
        if not avail_zones:
            continue
        any_avail = True
        lines.append(_game_header(g))
        for z in sorted(avail_zones, key=lambda x: x["name"]):
            price = f"  ${z['price']}" if z.get("price") else ""
            avail = _fmt_avail(z.get("available", -1))
            avail_s = f"  [{avail}]" if avail else ""
            lines.append(f"   • {z['name']}{price}{avail_s}")
        lines.append(f"   🔗 {g.get('schedule_url','')}")
        lines.append("")
    if not any_avail:
        lines.append("（目前所有目標區域皆售完）")
        lines.append("")
    lines.append("⏰ 8 小時後若仍無新釋出會再次提醒")
    lines.append("⚠️ 請手動前往購票，本程式不會自動下單")
    return send_line_message("\n".join(lines))


if __name__ == "__main__":
    notify_tickets([{
        "date": "2026-05-03", "weekday": "日", "opponent": "樂天",
        "venue": "洲際棒球場", "zone": "內野南C區下層", "price": 500,
        "game_url": "https://tix.ctbcsports.com/BROTHERS/UTK0205_?PERFORMANCE_ID=TEST",
    }])
