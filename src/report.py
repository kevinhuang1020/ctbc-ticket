"""即時餘票快照：跑一次完整掃描、印出當下所有目標區域的票況。

用法：
  PYTHONPATH=src python src/report.py
"""
from scraper import scrape_all
from filter import is_target_game, is_target_zone


def fmt_avail(n):
    if n == 0:
        return "售完"
    if n == -1:
        return "熱賣中"
    return f"{n} 張"


def main():
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

    print("\n" + "=" * 70)
    print(f"  中信兄弟假日主場 C/D/E/F 區票況快照（{len(target)} 場）")
    print("=" * 70)

    for g in target:
        print(f"\n📅 {g['date']}({g['weekday']}) {g['time']}  中信 vs {g['opponent']} @ {g['venue']}")
        # 同一場可能有多個 PERFORMANCE_ID（一般席不同票價組合），合併顯示
        zs = sorted(g["zones"], key=lambda z: (z["name"],))
        # 計算各狀態統計
        n_hot = sum(1 for z in zs if z["available"] == -1)
        n_sold = sum(1 for z in zs if z["available"] == 0)
        n_remain = sum(1 for z in zs if isinstance(z["available"], int) and z["available"] > 0)
        total = sum(z["available"] for z in zs if isinstance(z["available"], int) and z["available"] > 0)
        print(f"   小計：熱賣 {n_hot} 區、售完 {n_sold} 區、有具體餘票 {n_remain} 區（合計 {total} 張）")

        for z in zs:
            avail = fmt_avail(z["available"])
            price = f"${z['price']}" if z.get("price") else "  —  "
            print(f"     {z['name']:<28} {price:>6}   {avail}")

    print("\n" + "=" * 70)
    print(f"  完成 — {sum(len(g['zones']) for g in target)} 個區域")
    print("=" * 70)


if __name__ == "__main__":
    main()
