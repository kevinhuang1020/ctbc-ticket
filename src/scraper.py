"""tix.ctbcsports.com scraper（Playwright，三層）：

1. UTK0102_?TYPE=4         賽程列表 → PRODUCT_ID + STARTDATE
2. UTK0201_?PRODUCT_ID=... 場次/票種頁 → PERFORMANCE_ID
3. UTK0205_?PERFORMANCE_ID=... 區域票況頁 → 各區餘票

站台用 Service Worker 緩存，wait_until='domcontentloaded' + 等選擇器較可靠。
"""
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE = "https://tix.ctbcsports.com"
SCHEDULE_URL = f"{BASE}/BROTHERS/UTK0102_?TYPE=4"
WEEKDAY_TW = ["一", "二", "三", "四", "五", "六", "日"]


# ─────────────────────────────────────────
# Layer 1: 賽程列表
# ─────────────────────────────────────────
def parse_schedule_card(href, h1_text, h2_text):
    """從卡片三個欄位解析出結構化資料。"""
    m = re.search(r"PRODUCT_ID=([A-Za-z0-9]+)", href)
    product_id = m.group(1) if m else None

    m = re.search(r"STARTDATE=(\d{4})/(\d{1,2})/(\d{1,2})", href)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        dt = datetime(y, mo, d)
    else:
        # fallback：從 h2「2026/04/29 18:35」抓
        m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", h2_text)
        if not m:
            return None
        y, mo, d = (int(x) for x in m.groups())
        dt = datetime(y, mo, d)

    # 標題格式：「中華職棒37年例行賽樂天桃猿vs中信兄弟@洲際棒球場(家庭席)」
    title = h1_text.strip()
    opponent = ""
    venue = ""
    variant = ""

    m = re.search(r"例行賽(.+?)vs中信兄弟", title)
    if m:
        opponent = m.group(1).strip()

    m = re.search(r"@([^()（）]+)", title)
    if m:
        venue = m.group(1).strip()

    m = re.search(r"[（(]([^)）]+)[）)]", title)
    if m:
        variant = m.group(1).strip()

    return {
        "product_id": product_id,
        "date": dt.strftime("%Y-%m-%d"),
        "weekday_idx": dt.weekday(),
        "weekday": WEEKDAY_TW[dt.weekday()],
        "time": h2_text.strip(),
        "opponent": opponent,
        "venue": venue,
        "variant": variant,
        "title": title,
        "schedule_url": href if href.startswith("http") else BASE + "/BROTHERS/" + href.lstrip("/"),
    }


def fetch_schedule(page):
    page.goto(SCHEDULE_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("a[href*='UTK0201_'][href*='PRODUCT_ID=']", timeout=20000)
    except Exception:
        print("[scraper] 警告：20 秒內沒等到賽程卡片，繼續嘗試解析")
    page.wait_for_timeout(1500)

    games = []
    seen = set()
    cards = page.query_selector_all("a[href*='UTK0201_'][href*='PRODUCT_ID=']")
    for card in cards:
        href = card.get_attribute("href") or ""
        h1 = card.query_selector("h1")
        h2 = card.query_selector("h2")
        h1_text = h1.inner_text() if h1 else ""
        h2_text = h2.inner_text() if h2 else ""

        info = parse_schedule_card(href, h1_text, h2_text)
        if not info or not info["product_id"]:
            continue
        # 用 (product_id, date) 去重 — 同一場有「一般」「家庭席」會出現兩張卡片
        key = (info["product_id"], info["date"])
        if key in seen:
            continue
        seen.add(key)
        games.append(info)
    return games


# ─────────────────────────────────────────
# Layer 2: 場次 → PERFORMANCE_ID
# 結構：<button onclick="location.href='UTK0204_?PERFORMANCE_ID=...'">購買</button>
#       已售完則 onclick 指向 UTK0202_
# ─────────────────────────────────────────
def fetch_performances(page, schedule_url):
    page.goto(schedule_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("[onclick*='PERFORMANCE_ID']", timeout=15000)
    except Exception:
        return []
    page.wait_for_timeout(1000)

    # 同時抓「購買」「已售完」按鈕，以及該按鈕所在的 row（拿票種名稱）
    performances = []
    seen = set()
    rows = page.query_selector_all("tbody tr")
    for tr in rows:
        btn = tr.query_selector("[onclick*='PERFORMANCE_ID']")
        if not btn:
            continue
        oc = btn.get_attribute("onclick") or ""
        m = re.search(r"PERFORMANCE_ID=([A-Za-z0-9]+)", oc)
        if not m:
            continue
        pid = m.group(1)
        if pid in seen:
            continue
        seen.add(pid)

        btn_text = (btn.text_content() or "").strip()
        is_available = btn_text == "購買" or "購買" in btn_text
        # row 文字含名稱、票價
        row_text = (tr.text_content() or "").strip()
        # 票種名稱：通常包含「家庭席」「一般」等關鍵字
        is_family = "家庭席" in row_text
        # 票價：抓所有出現的價格
        prices = [int(x) for x in re.findall(r"\b\d{3,5}\b", row_text)]

        next_url = re.search(r"'(UTK020[24]_[^']+)'", oc)
        url_path = next_url.group(1) if next_url else ""
        full = BASE + "/BROTHERS/" + url_path if url_path else ""

        performances.append({
            "performance_id": pid,
            "available": is_available,
            "is_family": is_family,
            "prices": prices,
            "row_text": row_text[:200],
            "url": full,
        })
    return performances


# ─────────────────────────────────────────
# Layer 3: UTK0204_ 區域選擇頁
# 結構：<tr class="saleTr"><td>區域名</td><td>票價</td><td>空位</td></tr>
# 空位三種狀態：「熱賣中」(有票)、純數字 (剩餘張數)、「售完」
# ─────────────────────────────────────────
HOT = "熱賣中"
SOLD_OUT = "售完"


def parse_availability(text):
    """回傳 (available_int, raw_text)。
    available 規則：
      售完  → 0
      熱賣中 → -1（有票但不知道數量）
      數字   → 該數字
    """
    t = text.strip()
    if SOLD_OUT in t or "完售" in t:
        return 0, t
    if HOT in t:
        return -1, t
    m = re.search(r"\d+", t)
    if m:
        return int(m.group()), t
    return -1, t  # 解析不出來，當作有票（保守通知）


def fetch_zones(page, performance_url):
    page.goto(performance_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("tr.saleTr", timeout=15000)
    except Exception:
        return []

    # 等 saleTr 的 td[data-title='票區'] 真的填入內容
    try:
        page.wait_for_function(
            """() => {
                const tr = document.querySelector('tr.saleTr');
                if (!tr) return false;
                const td = tr.querySelector('td[data-title*="票區"]');
                return td && (td.textContent || '').trim().length > 0;
            }""",
            timeout=15000,
        )
    except Exception:
        return []

    zones = []
    # 用 data-title 屬性精準對應，避開 td[0] 是顏色塊的問題
    rows = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('tr.saleTr')).map(tr => {
            const tds = Array.from(tr.querySelectorAll('td'));
            const find = (k) => tds.find(td => (td.getAttribute('data-title') || '').includes(k));
            const get = (k) => {
                const el = find(k);
                return el ? (el.textContent || '').trim() : '';
            };
            return { name: get('票區'), price: get('票價'), avail: get('空位') };
        });
    }""")

    for row in rows:
        name = row["name"]
        try:
            price = int(re.sub(r"\D", "", row["price"])) if row["price"] else None
        except ValueError:
            price = None
        avail, raw = parse_availability(row["avail"])
        zones.append({
            "name": name,
            "price": price,
            "available": avail,
            "raw_avail": raw,
        })
    return zones


# ─────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────
def scrape_all(headless=True, depth="full", filter_fn=None):
    """
    depth:
      - "schedule": 只抓賽程列表（debug 用）
      - "performances": schedule + 每場的 PERFORMANCE_ID
      - "full": 三層全跑（含區域票況）
    filter_fn(game) -> bool: 在進第二層前篩掉不感興趣的場次（省時）
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="zh-TW")
        page = ctx.new_page()
        try:
            games = fetch_schedule(page)
            print(f"[scraper] L1 抓到 {len(games)} 場")

            if depth == "schedule":
                return games

            for g in games:
                if filter_fn and not filter_fn(g):
                    g["performances"] = []
                    g["zones"] = []
                    continue
                try:
                    perfs = fetch_performances(page, g["schedule_url"])
                    g["performances"] = perfs
                    print(f"[scraper] L2 {g['date']} {g['opponent']}@{g['venue']} → {len(perfs)} 個 performance")
                except Exception as e:
                    print(f"[scraper] L2 失敗 {g['product_id']}: {e}")
                    g["performances"] = []

                if depth != "full":
                    continue

                all_zones = []
                for perf in g["performances"]:
                    # 跳過：家庭席、整票種已售完
                    if perf.get("is_family"):
                        continue
                    if not perf.get("available"):
                        continue
                    if not perf.get("url"):
                        continue
                    try:
                        zs = fetch_zones(page, perf["url"])
                        for z in zs:
                            z["performance_id"] = perf["performance_id"]
                        all_zones.extend(zs)
                    except Exception as e:
                        print(f"[scraper] L3 失敗 {perf['performance_id']}: {e}")
                g["zones"] = all_zones
                print(f"[scraper] L3 {g['date']} → {len(all_zones)} 區")
        finally:
            ctx.close()
            browser.close()
        return games


if __name__ == "__main__":
    import json
    import sys
    depth = sys.argv[1] if len(sys.argv) > 1 else "schedule"
    games = scrape_all(headless=False, depth=depth)
    print(json.dumps(games, ensure_ascii=False, indent=2, default=str))
