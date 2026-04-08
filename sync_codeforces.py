import requests
from datetime import datetime, timedelta, timezone
import os.path
import json

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
DATA_FILE = "data/events.json"


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


# 📡 FETCH CONTESTS
def fetch_codeforces_contests():
    url = "https://codeforces.com/api/contest.list"
    response = requests.get(url)
    data = response.json()

    contests = data['result']

    now = datetime.now(timezone.utc).timestamp()
    limit = now + (7 * 24 * 60 * 60)

    upcoming = [
        c for c in contests
        if c['phase'] == 'BEFORE' and now <= c['startTimeSeconds'] <= limit
    ]

    upcoming.sort(key=lambda x: x['startTimeSeconds'])
    return upcoming


# 📂 LOAD SAVED EVENTS
def load_events():
    if not os.path.exists(DATA_FILE):
        return {}

    with open(DATA_FILE, "r") as f:
        return json.load(f)


# 💾 SAVE EVENTS
def save_events(events):
    with open(DATA_FILE, "w") as f:
        json.dump(events, f, indent=4)


# 📅 CREATE EVENT
def create_event(service, contest):
    start_time = datetime.fromtimestamp(
        contest['startTimeSeconds'], tz=timezone.utc
    )
    end_time = start_time + timedelta(seconds=contest['durationSeconds'])

    event = {
        'summary': f"{contest['name']} (Codeforces)",
        'description': f"https://codeforces.com/contest/{contest['id']}",
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'Asia/Kolkata',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'Asia/Kolkata',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 1440},
                {'method': 'popup', 'minutes': 60},
                {'method': 'popup', 'minutes': 15},
            ],
        },
    }

    created_event = service.events().insert(
        calendarId='primary',
        body=event
    ).execute()

    return created_event['id']





# 🔁 MAIN
def main():
    creds = authenticate()
    service = build('calendar', 'v3', credentials=creds)

    contests = fetch_codeforces_contests()
    saved_events = load_events()

    for contest in contests:
        contest_id = str(contest['id'])

        if contest_id in saved_events:
            print(f"⏭️ Skipped (already exists): {contest['name']}")
            continue

        event_id = create_event(service, contest)
        saved_events[contest_id] = event_id

        print(f"✅ Created: {contest['name']}")

    save_events(saved_events)


if __name__ == "__main__":
    main()