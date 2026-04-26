"""即時餘票快照：跑一次完整掃描、印出 + 推 LINE 所有目標區域的票況。
售完的不顯示。
與「上一次 report 執行結果」比對，標出變化。

用法：
  PYTHONPATH=src python src/report.py            # 印 + 推 LINE
  PYTHONPATH=src python src/report.py --no-line  # 只印不推
"""
import json
import sys
from pathlib import Path

from scraper import scrape_all
from filter import is_target_game, is_target_zone
from notifier import send_line_message

REPORT_STATE = Path("report_state.json")


def fmt_avail(n):
    if n == -1:
        return "熱賣中"
    return f"{n} 張"


def load_prev():
    if not REPORT_STATE.exists():
        return None  # None 表示「無上次資料」，避免把全部標成新增
    try:
        return json.loads(REPORT_STATE.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_curr(snapshot):
    REPORT_STATE.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def diff_mark(prev_val, curr_val):
    """回傳一個短標記字串。"""
    if prev_val is None:
        return "🆕"
    if prev_val == curr_val:
        return ""
    # 之前售完或不存在 → 現在有 → 視為新出現（理論上 None 已處理上面）
    if prev_val == 0:
        return "🆕"
    if prev_val == -1 and isinstance(curr_val, int) and curr_val > 0:
        return "(熱賣→具體)"
    if isinstance(prev_val, int) and prev_val > 0 and curr_val == -1:
        return "(具體→熱賣)"
    if isinstance(prev_val, int) and isinstance(curr_val, int):
        delta = curr_val - prev_val
        return f"⬆️+{delta}" if delta > 0 else f"⬇️{delta}"
    return ""


def main():
    no_line = "--no-line" in sys.argv

    prev = load_prev()
    is_first = prev is None
    if prev is None:
        prev = {}

    games = scrape_all(headless=True)

    target = []
    for g in games:
        if not is_target_game(g):
            continue
        zs = [z for z in g.get("zones", []) if is_target_zone(z["name"])]
        if zs:
            g = {**g, "zones": zs}
            target.append(g)
    target.sort(key=lambda g: g["date"])

    # 蒐集本次快照（key = date|zone_name → available）只記非售完
    curr_snapshot = {}
    for g in target:
        for z in g["zones"]:
            if z["available"] == 0:
                continue
            curr_snapshot[f"{g['date']}|{z['name']}"] = z["available"]

    # 找「本次新售完」：上次有票但這次不在快照裡
    newly_sold = []
    for key, prev_val in prev.items():
        if key not in curr_snapshot:
            newly_sold.append(key)
    newly_sold.sort()

    # 組訊息
    out_console = []
    out_line = []
    diff_note = "" if is_first else f"  (對比上次 {len(prev)} 區)"
    out_console.append("=" * 70)
    out_console.append(f"  中信兄弟假日主場 C/D/E/F 區票況快照（{len(target)} 場）{diff_note}")
    out_console.append("=" * 70)
    out_line.append(f"🎫 中信兄弟假日主場票況快照（{len(target)} 場）{diff_note}")
    if is_first:
        out_console.append("  (首次執行，無比對基準)")
        out_line.append("(首次執行，無比對基準)")

    for g in target:
        zs = sorted(
            [z for z in g["zones"] if z["available"] != 0],
            key=lambda z: z["name"],
        )
        if not zs:
            continue

        n_hot = sum(1 for z in zs if z["available"] == -1)
        n_remain = sum(1 for z in zs if isinstance(z["available"], int) and z["available"] > 0)
        total = sum(z["available"] for z in zs if isinstance(z["available"], int) and z["available"] > 0)

        header = f"\n📅 {g['date']}({g['weekday']}) {g['time']}  中信 vs {g['opponent']} @ {g['venue']}"
        summary = f"   熱賣 {n_hot} 區、有票 {n_remain} 區（具體合計 {total} 張）"
        url_line = f"   🔗 {g.get('schedule_url', '')}"

        out_console.append(header)
        out_console.append(summary)
        out_console.append(url_line)
        out_line.append(header)
        out_line.append(summary)
        out_line.append(url_line)

        for z in zs:
            avail = fmt_avail(z["available"])
            price = f"${z['price']}" if z.get("price") else "—"
            mark = "" if is_first else diff_mark(prev.get(f"{g['date']}|{z['name']}"), z["available"])
            mark_str = f"  {mark}" if mark else ""
            out_console.append(f"     {z['name']:<28} {price:>6}   {avail}{mark_str}")
            out_line.append(f"  • {z['name']}  {price}  {avail}{mark_str}")

    # 新售完區段
    if newly_sold and not is_first:
        out_console.append("\n" + "-" * 70)
        out_console.append(f"  ❌ 本次新售完（{len(newly_sold)} 區）")
        out_console.append("-" * 70)
        out_line.append(f"\n❌ 本次新售完（{len(newly_sold)} 區）")
        for k in newly_sold:
            date_, name = k.split("|", 1)
            prev_val = prev[k]
            prev_str = "熱賣中" if prev_val == -1 else f"{prev_val} 張"
            line = f"  {date_}  {name}  (上次：{prev_str})"
            out_console.append(line)
            out_line.append(line)

    out_console.append("\n" + "=" * 70)
    out_console.append(f"  完成 — {len(curr_snapshot)} 個有票區域")
    out_console.append("=" * 70)
    out_line.append(f"\n⚠️ 售完區未列出，請手動前往購票")

    print("\n".join(out_console))

    if not no_line:
        ok = send_line_message("\n".join(out_line))
        print(f"\n[report] LINE 推播 {'成功' if ok else '失敗或已跳過'}")

    save_curr(curr_snapshot)


if __name__ == "__main__":
    main()
