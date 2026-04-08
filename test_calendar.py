from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import datetime
import os.path

SCOPES = ['https://www.googleapis.com/auth/calendar']

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

def create_event():
    creds = authenticate()
    service = build('calendar', 'v3', credentials=creds)

    event = {
        'summary': 'Test Event 🚀',
        'description': 'If you see this, setup works!',
        'start': {
            'dateTime': (datetime.datetime.now() + datetime.timedelta(minutes=2)).isoformat(),
            'timeZone': 'Asia/Kolkata',
        },
        'end': {
            'dateTime': (datetime.datetime.now() + datetime.timedelta(minutes=32)).isoformat(),
            'timeZone': 'Asia/Kolkata',
        },
    }

    event = service.events().insert(calendarId='primary', body=event).execute()
    print("Event created:", event.get('htmlLink'))

create_event()