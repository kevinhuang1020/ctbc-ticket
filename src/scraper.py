"""多站票務 scraper（Playwright，三層）。

支援站台：
- brothers (tix.ctbcsports.com/BROTHERS)：賽程列表為 card（h1=標題、h2=時間）
- guardians (guardians.fami.life)：賽程列表為簡單 anchor，僅含對手隊名 + STARTDATE

L2 / L3 結構兩站相同：
- L2 UTK0201_?PRODUCT_ID=...&STARTDATE=...：tbody tr → onclick='UTK0204_?PERFORMANCE_ID=...'
- L3 UTK0204_?PERFORMANCE_ID=...：tr.saleTr → td[data-title='票區/票價/空位']
"""
import re
import urllib.parse
from datetime import datetime
from playwright.sync_api import sync_playwright

WEEKDAY_TW = ["一", "二", "三", "四", "五", "六", "日"]
HOT = "熱賣中"
SOLD_OUT = "售完"

# 主場館關鍵字（用於從 L2 row text 推斷 venue，並判斷是否主場）
VENUE_KEYWORDS = ["洲際", "大巨蛋", "新莊"]


# ─────────────────────────────────────────
# 站台設定
# ─────────────────────────────────────────
SITES = [
    {
        "key": "brothers",
        "home_team": "中信兄弟",
        "base": "https://tix.ctbcsports.com",
        "schedule_url": "https://tix.ctbcsports.com/BROTHERS/UTK0102_?TYPE=4",
    },
    {
        "key": "guardians",
        "home_team": "富邦悍將",
        "base": "https://guardians.fami.life",
        "schedule_url": "https://guardians.fami.life/UTK0101_",
    },
]


# ─────────────────────────────────────────
# Layer 1：賽程列表
# ─────────────────────────────────────────
def _parse_brothers_card(href, h1_text, h2_text, site):
    """中信：card 含 h1（標題：「...例行賽XXvs中信兄弟@洲際棒球場(家庭席)」）+ h2（時間）。"""
    m = re.search(r"PRODUCT_ID=([A-Za-z0-9]+)", href)
    product_id = m.group(1) if m else None

    m = re.search(r"STARTDATE=(\d{4})/(\d{1,2})/(\d{1,2})", href)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        dt = datetime(y, mo, d)
    else:
        m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", h2_text)
        if not m:
            return None
        y, mo, d = (int(x) for x in m.groups())
        dt = datetime(y, mo, d)

    title = h1_text.strip()
    opponent = ""
    venue = ""
    variant = ""
    m = re.search(rf"例行賽(.+?)vs{site['home_team']}", title)
    if m:
        opponent = m.group(1).strip()
    m = re.search(r"@([^()（）]+)", title)
    if m:
        venue = m.group(1).strip()
    m = re.search(r"[（(]([^)）]+)[）)]", title)
    if m:
        variant = m.group(1).strip()

    schedule_url = href if href.startswith("http") else site["base"] + "/BROTHERS/" + href.lstrip("/")
    return {
        "source": site["key"],
        "home_team": site["home_team"],
        "product_id": product_id,
        "date": dt.strftime("%Y-%m-%d"),
        "weekday_idx": dt.weekday(),
        "weekday": WEEKDAY_TW[dt.weekday()],
        "time": h2_text.strip(),
        "opponent": opponent,
        "venue": venue,
        "variant": variant,
        "title": title,
        "schedule_url": schedule_url,
    }


def fetch_schedule_brothers(page, site):
    page.goto(site["schedule_url"], wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("a[href*='UTK0201_'][href*='PRODUCT_ID=']", timeout=20000)
    except Exception:
        print(f"[scraper:{site['key']}] 警告：20 秒內沒等到賽程卡片")
    page.wait_for_timeout(1500)

    games = []
    seen = set()
    for card in page.query_selector_all("a[href*='UTK0201_'][href*='PRODUCT_ID=']"):
        href = card.get_attribute("href") or ""
        h1 = card.query_selector("h1")
        h2 = card.query_selector("h2")
        h1_text = h1.inner_text() if h1 else ""
        h2_text = h2.inner_text() if h2 else ""
        info = _parse_brothers_card(href, h1_text, h2_text, site)
        if not info or not info["product_id"]:
            continue
        key = (info["product_id"], info["date"])
        if key in seen:
            continue
        seen.add(key)
        games.append(info)
    return games


def fetch_schedule_guardians(page, site):
    """富邦：anchor text = 對手隊名，href 含 PRODUCT_ID + STARTDATE，venue 須由 L2 補。"""
    page.goto(site["schedule_url"], wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("a[href*='UTK0201_'][href*='PRODUCT_ID=']", timeout=20000)
    except Exception:
        print(f"[scraper:{site['key']}] 警告：20 秒內沒等到賽程卡片")
    page.wait_for_timeout(1500)

    games = []
    seen = set()
    for card in page.query_selector_all("a[href*='UTK0201_'][href*='PRODUCT_ID=']"):
        href = card.get_attribute("href") or ""
        m = re.search(r"STARTDATE=(\d{4})/(\d{1,2})/(\d{1,2})", href)
        if not m:
            continue
        y, mo, d = (int(x) for x in m.groups())
        dt = datetime(y, mo, d)
        date_str = dt.strftime("%Y-%m-%d")
        opp = (card.inner_text() or "").strip()
        if not opp:
            continue
        m2 = re.search(r"PRODUCT_ID=([A-Za-z0-9]+)", href)
        product_id = m2.group(1) if m2 else None
        key = (date_str, opp)
        if key in seen:
            continue
        seen.add(key)
        schedule_url = href if href.startswith("http") else site["base"] + "/" + href.lstrip("/")
        games.append({
            "source": site["key"],
            "home_team": site["home_team"],
            "product_id": product_id,
            "date": date_str,
            "weekday_idx": dt.weekday(),
            "weekday": WEEKDAY_TW[dt.weekday()],
            "time": "",
            "opponent": opp,
            "venue": "",      # 由 L2 row text 補
            "variant": "",
            "title": f"{opp}vs{site['home_team']}",
            "schedule_url": schedule_url,
        })
    return games


SCHEDULE_FETCHERS = {
    "brothers": fetch_schedule_brothers,
    "guardians": fetch_schedule_guardians,
}


# ─────────────────────────────────────────
# Layer 2：場次 → PERFORMANCE_ID
# ─────────────────────────────────────────
def _infer_venue(text):
    for kw in VENUE_KEYWORDS:
        if kw in text:
            # 把出現上下文盡量回傳完整館名
            if kw == "洲際":
                return "臺中洲際棒球場"
            if kw == "大巨蛋":
                return "臺北大巨蛋"
            if kw == "新莊":
                return "新莊棒球場"
    return ""


def fetch_performances(page, schedule_url):
    page.goto(schedule_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("[onclick*='PERFORMANCE_ID']", timeout=15000)
    except Exception:
        return [], ""
    page.wait_for_timeout(1000)

    performances = []
    seen = set()
    first_venue = ""

    for tr in page.query_selector_all("tbody tr"):
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
        row_text = (tr.text_content() or "").strip()
        is_family = "家庭席" in row_text or "派對席" in row_text or "PARTY ZONE" in row_text
        prices = [int(x) for x in re.findall(r"\b\d{3,5}\b", row_text)]
        row_venue = _infer_venue(row_text)
        if row_venue and not first_venue:
            first_venue = row_venue

        next_url = re.search(r"'(UTK020[24]_[^']+)'", oc)
        url_path = next_url.group(1) if next_url else ""
        full = urllib.parse.urljoin(schedule_url, url_path) if url_path else ""

        performances.append({
            "performance_id": pid,
            "available": is_available,
            "is_family": is_family,
            "prices": prices,
            "row_text": row_text[:200],
            "venue": row_venue,
            "url": full,
        })
    return performances, first_venue


# ─────────────────────────────────────────
# Layer 3：UTK0204_ 區域票況
# ─────────────────────────────────────────
def parse_availability(text):
    t = text.strip()
    if SOLD_OUT in t or "完售" in t:
        return 0, t
    if HOT in t:
        return -1, t
    m = re.search(r"\d+", t)
    if m:
        return int(m.group()), t
    return -1, t


def fetch_zones(page, performance_url):
    page.goto(performance_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("tr.saleTr", timeout=15000)
    except Exception:
        return []
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

    rows = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('tr.saleTr')).map(tr => {
            const tds = Array.from(tr.querySelectorAll('td'));
            const find = (k) => tds.find(td => (td.getAttribute('data-title') || '').includes(k));
            const get = (k) => { const el = find(k); return el ? (el.textContent || '').trim() : ''; };
            return { name: get('票區'), price: get('票價'), avail: get('空位') };
        });
    }""")

    zones = []
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
    """跑所有站台的 L1/L2/L3，回傳合併後的 games list。"""
    all_games = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="zh-TW")
        page = ctx.new_page()
        try:
            for site in SITES:
                fetcher = SCHEDULE_FETCHERS[site["key"]]
                try:
                    games = fetcher(page, site)
                    print(f"[scraper:{site['key']}] L1 抓到 {len(games)} 場")
                except Exception as e:
                    print(f"[scraper:{site['key']}] L1 失敗: {e}")
                    games = []

                if depth == "schedule":
                    all_games.extend(games)
                    continue

                for g in games:
                    if filter_fn and not filter_fn(g):
                        g["performances"] = []
                        g["zones"] = []
                        continue
                    try:
                        perfs, body_venue = fetch_performances(page, g["schedule_url"])
                        g["performances"] = perfs
                        if not g.get("venue") and body_venue:
                            g["venue"] = body_venue
                        print(f"[scraper:{site['key']}] L2 {g['date']} {g['opponent']}@{g['venue']} → {len(perfs)} 個 performance")
                    except Exception as e:
                        print(f"[scraper:{site['key']}] L2 失敗 {g.get('product_id')}: {e}")
                        g["performances"] = []

                    if depth != "full":
                        continue

                    all_zones = []
                    for perf in g["performances"]:
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
                            print(f"[scraper:{site['key']}] L3 失敗 {perf['performance_id']}: {e}")
                    g["zones"] = all_zones
                    print(f"[scraper:{site['key']}] L3 {g['date']} → {len(all_zones)} 區")

                all_games.extend(games)
        finally:
            ctx.close()
            browser.close()
    return all_games


if __name__ == "__main__":
    import json
    import sys
    depth = sys.argv[1] if len(sys.argv) > 1 else "schedule"
    games = scrape_all(headless=False, depth=depth)
    print(json.dumps(games, ensure_ascii=False, indent=2, default=str))
