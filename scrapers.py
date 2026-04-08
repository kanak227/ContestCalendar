import requests
import logging
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
