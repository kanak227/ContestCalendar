import requests
import logging
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Setup logging
logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

def fetch_codeforces(days_limit=7):
    """Fetch upcoming contests from Codeforces."""
    url = "https://codeforces.com/api/contest.list"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()['result']
    except Exception as e:
        logger.error(f"Failed to fetch Codeforces contests: {e}")
        return []

    now = datetime.now(timezone.utc)
    limit = now + timedelta(days=days_limit)

    contests = []
    for c in data:
        if c['phase'] != 'BEFORE':
            continue

        start_utc = datetime.fromtimestamp(c['startTimeSeconds'], tz=timezone.utc)

        if not (now <= start_utc <= limit):
            continue

        start = start_utc.astimezone(IST)
        end = start + timedelta(seconds=c['durationSeconds'])

        contests.append({
            "id": f"cf_{c['id']}",
            "name": c['name'],
            "url": f"https://codeforces.com/contest/{c['id']}",
            "start": start,
            "end": end
        })

    contests.sort(key=lambda x: x['start'])
    return contests

def fetch_leetcode(days_limit=7):
    """Fetch upcoming contests from LeetCode."""
    url = "https://leetcode.com/graphql"
    query = {
        "query": """
        query {
          allContests {
            title
            titleSlug
            startTime
            duration
          }
        }
        """
    }

    try:
        response = requests.post(url, json=query, timeout=10)
        response.raise_for_status()
        data = response.json()['data']['allContests']
    except Exception as e:
        logger.error(f"Failed to fetch LeetCode contests: {e}")
        return []

    now = datetime.now(timezone.utc)
    limit = now + timedelta(days=days_limit)

    contests = []
    for c in data:
        start_utc = datetime.fromtimestamp(c['startTime'], tz=timezone.utc)

        if not (now <= start_utc <= limit):
            continue

        start = start_utc.astimezone(IST)
        end = start + timedelta(seconds=c['duration'])

        contests.append({
            "id": f"lc_{c['titleSlug']}",
            "name": c['title'],
            "url": f"https://leetcode.com/contest/{c['titleSlug']}",
            "start": start,
            "end": end
        })

    contests.sort(key=lambda x: x['start'])
    return contests

def fetch_codechef(days_limit=7):
    """Fetch upcoming contests from CodeChef."""
    url = "https://www.codechef.com/api/list/contests/all"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"Failed to fetch CodeChef contests: {e}")
        return []

    contests = data.get('future_contests', [])
    now = datetime.now(timezone.utc)
    limit = now + timedelta(days=days_limit)

    contests_list = []
    for c in contests:
        try:
            start_naive = datetime.strptime(c['contest_start_date'], "%d %b %Y %H:%M:%S")
            start = start_naive.replace(tzinfo=IST)  # already IST
            
            if not (now <= start.astimezone(timezone.utc) <= limit):
                continue

            end = start + timedelta(minutes=int(c['contest_duration']))

            contests_list.append({
                "id": f"cc_{c['contest_code']}",
                "name": c['contest_name'],
                "url": f"https://www.codechef.com/{c['contest_code']}",
                "start": start,
                "end": end
            })
        except (ValueError, KeyError) as e:
            logger.warning(f"Skipping malformed CodeChef contest data: {e}")
            continue

    contests_list.sort(key=lambda x: x['start'])
    return contests_list


class AtCoderUpcomingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self._in_upcoming = False
        self._upcoming_div_depth = 0
        self._in_row = False
        self._in_cell = False
        self._in_contest_link = False
        self._cell_parts = []
        self._row_cells = []
        self._contest_href = None
        self._contest_title_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and attrs.get("id") == "contest-table-upcoming":
            self._in_upcoming = True
            self._upcoming_div_depth = 1
            return

        if not self._in_upcoming:
            return

        if tag == "div":
            self._upcoming_div_depth += 1
        elif tag == "tr":
            self._in_row = True
            self._row_cells = []
            self._contest_href = None
            self._contest_title_parts = []
        elif self._in_row and tag == "td":
            self._in_cell = True
            self._cell_parts = []
        elif self._in_cell and tag == "a" and attrs.get("href", "").startswith("/contests/"):
            self._contest_href = attrs["href"]
            self._in_contest_link = True

    def handle_endtag(self, tag):
        if not self._in_upcoming:
            return

        if tag == "a" and self._in_contest_link:
            self._in_contest_link = False
        elif tag == "td" and self._in_cell:
            self._row_cells.append(" ".join("".join(self._cell_parts).split()))
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._contest_href and len(self._row_cells) >= 3:
                self.rows.append({
                    "start": self._row_cells[0],
                    "title": " ".join("".join(self._contest_title_parts).split()),
                    "href": self._contest_href,
                    "duration": self._row_cells[2],
                })
            self._in_row = False
        elif tag == "div":
            self._upcoming_div_depth -= 1
            if self._upcoming_div_depth <= 0:
                self._in_upcoming = False

    def handle_data(self, data):
        if not self._in_cell:
            return
        self._cell_parts.append(data)
        if self._in_contest_link:
            self._contest_title_parts.append(data)


def parse_atcoder_duration(value):
    hours, minutes = value.strip().split(":", 1)
    return timedelta(hours=int(hours), minutes=int(minutes))


def fetch_atcoder(days_limit=7):
    """Fetch upcoming contests from AtCoder."""
    url = "https://atcoder.jp/contests/?lang=en"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch AtCoder contests: {e}")
        return []

    parser = AtCoderUpcomingParser()
    try:
        parser.feed(response.text)
    except Exception as e:
        logger.error(f"Failed to parse AtCoder contests: {e}")
        return []

    now = datetime.now(timezone.utc)
    limit = now + timedelta(days=days_limit)

    contests = []
    for c in parser.rows:
        try:
            start_jst = datetime.strptime(c["start"], "%Y-%m-%d %H:%M:%S%z")
            start_utc = start_jst.astimezone(timezone.utc)

            if not (now <= start_utc <= limit):
                continue

            contest_id = c["href"].rstrip("/").split("/")[-1]
            start = start_utc.astimezone(IST)
            end = start + parse_atcoder_duration(c["duration"])

            contests.append({
                "id": f"ac_{contest_id}",
                "name": c["title"],
                "url": f"https://atcoder.jp{c['href']}",
                "start": start,
                "end": end
            })
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"Skipping malformed AtCoder contest data: {e}")
            continue

    contests.sort(key=lambda x: x['start'])
    return contests

