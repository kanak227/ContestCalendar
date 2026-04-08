import requests
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
DATA_FILE = "data/events.json"

IST = ZoneInfo("Asia/Kolkata")


# 🔐 AUTH
def authenticate():
    creds = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds


# 📂 LOAD
def load_events():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


# 💾 SAVE
def save_events(events):
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(events, f, indent=4)


# 🔔 EVENT TEMPLATE
def build_event(summary, description, start, end, color_id=None):
    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start.isoformat(),
            'timeZone': 'Asia/Kolkata'
        },
        'end': {
            'dateTime': end.isoformat(),
            'timeZone': 'Asia/Kolkata'
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }
    if color_id:
        event['colorId'] = color_id
    return event


# 🔵 CODEFORCES
def fetch_codeforces():
    url = "https://codeforces.com/api/contest.list"
    data = requests.get(url).json()['result']

    now = datetime.now(timezone.utc)
    limit = now + timedelta(days=7)

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


# 🟡 LEETCODE
def fetch_leetcode():
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

    data = requests.post(url, json=query).json()['data']['allContests']

    now = datetime.now(timezone.utc)
    limit = now + timedelta(days=7)

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


# 🔴 CODECHEF
def fetch_codechef():
    url = "https://www.codechef.com/api/list/contests/all"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    response = requests.get(url, headers=headers)

    try:
        data = response.json()
    except:
        print("❌ CodeChef blocked request")
        return []

    contests = data['future_contests']

    now = datetime.now(timezone.utc)
    limit = now + timedelta(days=7)

    contests_list = []

    for c in contests:
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

    contests_list.sort(key=lambda x: x['start'])
    return contests_list


# 🚀 MAIN
def main():
    creds = authenticate()
    service = build('calendar', 'v3', credentials=creds)

    saved = load_events()

    all_contests = (
        fetch_codeforces() +
        fetch_leetcode() +
        fetch_codechef()
    )

    for c in all_contests:
        # 🎨 Assign colors based on platform
        color_id = None
        if c['id'].startswith('cf_'):
            color_id = '3'   # Blueberry (Codeforces)
        elif c['id'].startswith('lc_'):
            color_id = '5'   # Banana (LeetCode)
        elif c['id'].startswith('cc_'):
            color_id = '7'  # Tomato (CodeChef)

        event = build_event(c['name'], c['url'], c['start'], c['end'], color_id)
        
        if c['id'] in saved:
            event_id = saved[c['id']]
            try:
                service.events().update(
                    calendarId='primary',
                    eventId=event_id,
                    body=event
                ).execute()
                print(f"🔄 Updated: {c['name']} ({c['start'].strftime('%d %b %H:%M')})")
            except Exception as e:
                print(f"❌ Failed to update {c['name']}: {e}")
            continue

        created = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()

        saved[c['id']] = created['id']
        print(f"✅ Added: {c['name']} ({c['start'].strftime('%d %b %H:%M')})")

    save_events(saved)


if __name__ == "__main__":
    main()