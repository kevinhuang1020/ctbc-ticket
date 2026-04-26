"""即時餘票快照：跑一次完整掃描、印出 + 推 LINE 所有目標區域的票況。
售完的不顯示。

用法：
  PYTHONPATH=src python src/report.py            # 印 + 推 LINE
  PYTHONPATH=src python src/report.py --no-line  # 只印不推
"""
import sys

from scraper import scrape_all
from filter import is_target_game, is_target_zone
from notifier import send_line_message


def fmt_avail(n):
    if n == -1:
        return "熱賣中"
    return f"{n} 張"


def build_lines(target):
    """回傳 (console_lines, line_lines) — 兩者格式略不同（console 對齊較寬）。"""
    out_console = []
    out_line = []

    out_console.append("=" * 70)
    out_console.append(f"  中信兄弟假日主場 C/D/E/F 區票況快照（{len(target)} 場）")
    out_console.append("=" * 70)

    out_line.append(f"🎫 中信兄弟假日主場票況快照（{len(target)} 場）")

    for g in target:
        zs = sorted(
            [z for z in g["zones"] if z["available"] != 0],  # 排除售完
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
            out_console.append(f"     {z['name']:<28} {price:>6}   {avail}")
            out_line.append(f"  • {z['name']}  {price}  {avail}")

    out_console.append("\n" + "=" * 70)
    out_console.append(f"  完成 — {sum(len([z for z in g['zones'] if z['available'] != 0]) for g in target)} 個有票區域")
    out_console.append("=" * 70)

    out_line.append("\n⚠️ 售完區域未列出，請手動前往購票")
    return out_console, out_line


def main():
    no_line = "--no-line" in sys.argv

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

    console_lines, line_lines = build_lines(target)
    print("\n".join(console_lines))

    if not no_line:
        ok = send_line_message("\n".join(line_lines))
        print(f"\n[report] LINE 推播 {'成功' if ok else '失敗或已跳過'}")


if __name__ == "__main__":
    main()
