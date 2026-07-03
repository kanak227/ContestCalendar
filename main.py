import json
import os
import logging
import argparse
import hashlib
from datetime import datetime, timedelta, timezone
from googleapiclient.errors import HttpError

from scrapers import fetch_codeforces, fetch_leetcode, fetch_codechef, fetch_atcoder
from calendar_client import authenticate, get_calendar_service, build_event

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("sync.log")
    ]
)
logger = logging.getLogger(__name__)

DATA_FILE = "data/events.json"
CALENDAR_ID = "primary"


def load_saved_events():
    """Load previously saved event IDs from local storage."""
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load saved events: {e}")
        return {}


def save_events(events):
    """Save event IDs to local storage."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(events, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save events: {e}")


def generate_google_event_id(contest_id):
    """
    Generate a deterministic, valid Google Calendar event ID from a contest ID.
    Google Calendar event ID requirements:
    - Characters allowed: lowercase letters a-v, digits 0-9, and characters -_ (hyphens, underscores).
    - Length: 5 to 1024 characters.
    We use md5 hash of contest_id which produces a 32-character hex string (0-9, a-f).
    Since f is within v, this is 100% compliant.
    """
    return hashlib.md5(contest_id.encode("utf-8")).hexdigest()


def cleanup_saved_events(saved, service):
    """
    Remove past events from saved events dict and normalize values to dict format:
    {"event_id": str, "end": str (ISO 8601)}
    """
    now = datetime.now(timezone.utc)
    updated_saved = {}
    changed = False

    for contest_id, value in list(saved.items()):
        event_id = None
        end_time_str = None

        if isinstance(value, str):
            event_id = value
            try:
                event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
                end_time_str = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
                changed = True
            except Exception as e:
                logger.info(f"Removing legacy event {contest_id} ({event_id}) because it could not be fetched: {e}")
                changed = True
                continue
        elif isinstance(value, dict):
            event_id = value.get("event_id")
            end_time_str = value.get("end")

        if not event_id or not end_time_str:
            changed = True
            continue

        try:
            end_dt = parse_calendar_datetime(end_time_str)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)

            if end_dt < now:
                logger.info(f"Clearing past event: {contest_id} (ended at {end_time_str})")
                changed = True
                continue

            updated_saved[contest_id] = {
                "event_id": event_id,
                "end": end_time_str
            }
        except Exception as e:
            logger.warning(f"Failed to parse end time {end_time_str!r} for {contest_id}, removing: {e}")
            changed = True
            continue

    return updated_saved, changed


def get_platform_color(contest_id):
    """Get color ID based on the platform."""
    if contest_id.startswith("cf_"):
        return "3"   # Blueberry (Codeforces)
    if contest_id.startswith("lc_"):
        return "5"   # Banana (LeetCode)
    if contest_id.startswith("cc_"):
        return "7"   # Tomato (CodeChef)
    if contest_id.startswith("ac_"):
        return "10"  # Basil (AtCoder)
    return None


def parse_calendar_datetime(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def datetimes_match(left, right):
    if left.tzinfo is None:
        left = left.replace(tzinfo=timezone.utc)
    if right.tzinfo is None:
        right = right.replace(tzinfo=timezone.utc)
    return left.astimezone(timezone.utc) == right.astimezone(timezone.utc)


def event_has_contest_id(event, contest_id):
    private_props = event.get("extendedProperties", {}).get("private", {})
    return private_props.get("contest_id") == contest_id


def event_matches_contest(event, contest):
    if event_has_contest_id(event, contest['id']):
        return True

    event_start = event.get("start", {}).get("dateTime")
    if not event_start:
        return False

    try:
        starts_at_same_time = datetimes_match(parse_calendar_datetime(event_start), contest['start'])
    except ValueError:
        return False

    return (
        starts_at_same_time
        and event.get("summary") == contest['name']
        and event.get("description") == contest['url']
    )


def list_matching_events(service, contest):
    start = (contest['start'] - timedelta(minutes=5)).isoformat()
    end = (contest['end'] + timedelta(minutes=5)).isoformat()

    matches = []
    try:
        tagged = service.events().list(
            calendarId=CALENDAR_ID,
            privateExtendedProperty=f"contest_id={contest['id']}",
            singleEvents=True,
            showDeleted=False,
            timeMin=start,
            timeMax=end,
        ).execute().get("items", [])
        matches.extend(event for event in tagged if event_has_contest_id(event, contest['id']))
    except Exception as e:
        logger.warning(f"Failed to search tagged calendar events for {contest['id']}: {e}")

    try:
        nearby = service.events().list(
            calendarId=CALENDAR_ID,
            singleEvents=True,
            showDeleted=False,
            timeMin=start,
            timeMax=end,
        ).execute().get("items", [])
        known_ids = {event.get("id") for event in matches}
        matches.extend(
            event for event in nearby
            if event.get("id") not in known_ids and event_matches_contest(event, contest)
        )
    except Exception as e:
        logger.warning(f"Failed to search nearby calendar events for {contest['id']}: {e}")

    return matches


def remember_event(saved, contest, event_id):
    saved[contest["id"]] = {
        "event_id": event_id,
        "end": contest['end'].isoformat()
    }


def update_calendar_event(service, event_id, event_body):
    body = dict(event_body)
    body.pop("id", None)
    return service.events().update(
        calendarId=CALENDAR_ID,
        eventId=event_id,
        body=body
    ).execute()


def insert_calendar_event(service, event_id, event_body):
    body = dict(event_body)
    body["id"] = event_id
    return service.events().insert(
        calendarId=CALENDAR_ID,
        body=body
    ).execute()


def format_contest_start(contest):
    return contest["start"].strftime("%d %b %H:%M")


def find_saved_event_id(saved, contest_id):
    value = saved.get(contest_id)
    if isinstance(value, dict):
        return value.get("event_id")
    if isinstance(value, str):
        return value
    return None


def main():
    parser = argparse.ArgumentParser(description="Sync contests to Google Calendar.")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without modifying the calendar.")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look ahead for contests.")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("Running in DRY-RUN mode. No changes will be made to the calendar.")

    try:
        creds = authenticate()
        service = get_calendar_service(creds)
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return

    saved = load_saved_events()

    logger.info("Cleaning up and normalizing saved events...")
    saved, _ = cleanup_saved_events(saved, service)

    logger.info("Fetching contests...")
    all_contests = (
        fetch_codeforces(days_limit=args.days) +
        fetch_leetcode(days_limit=args.days) +
        fetch_codechef(days_limit=args.days) +
        fetch_atcoder(days_limit=args.days)
    )

    logger.info(f"Found {len(all_contests)} total upcoming contests.")

    for contest in all_contests:
        event_id = find_saved_event_id(saved, contest["id"])
        deterministic_id = generate_google_event_id(contest["id"])
        color_id = get_platform_color(contest["id"])
        event_body = build_event(
            contest['name'],
            contest['url'],
            contest['start'],
            contest['end'],
            color_id,
            contest_id=contest["id"]
        )

        if event_id:
            if args.dry_run:
                logger.info(f"[DRY-RUN] Would update: {contest['name']} ({format_contest_start(contest)})")
                continue

            try:
                update_calendar_event(service, event_id, event_body)
                remember_event(saved, contest, event_id)
                logger.info(f"Updated: {contest['name']} ({format_contest_start(contest)})")
                continue
            except HttpError as e:
                if e.resp.status != 404:
                    logger.error(f"Failed to update {contest['name']}: {e}")
                    continue
                logger.info(f"Saved event {event_id} for {contest['name']} was not found. Searching calendar before inserting...")
            except Exception as e:
                logger.error(f"Failed to update {contest['name']}: {e}")
                continue

        matching_events = list_matching_events(service, contest)
        if matching_events:
            adopted_id = matching_events[0]["id"]
            if len(matching_events) > 1:
                duplicate_ids = [event.get("id") for event in matching_events[1:]]
                logger.warning(f"Found duplicate existing events for {contest['name']}: {duplicate_ids}")

            if args.dry_run:
                logger.info(f"[DRY-RUN] Would adopt/update existing calendar event: {contest['name']}")
                continue

            try:
                update_calendar_event(service, adopted_id, event_body)
                remember_event(saved, contest, adopted_id)
                logger.info(f"Adopted existing calendar event: {contest['name']} ({format_contest_start(contest)})")
            except Exception as e:
                logger.error(f"Failed to adopt existing event for {contest['name']}: {e}")
            continue

        if args.dry_run:
            logger.info(f"[DRY-RUN] Would add: {contest['name']} ({format_contest_start(contest)})")
            continue

        try:
            created = insert_calendar_event(service, deterministic_id, event_body)
            remember_event(saved, contest, created["id"])
            logger.info(f"Added: {contest['name']} ({format_contest_start(contest)})")
        except HttpError as e:
            if e.resp.status == 409:
                logger.info(f"Event for {contest['name']} already exists by deterministic ID. Updating it...")
                try:
                    update_calendar_event(service, deterministic_id, event_body)
                    remember_event(saved, contest, deterministic_id)
                    logger.info(f"Updated (resolved conflict): {contest['name']} ({format_contest_start(contest)})")
                except Exception as update_err:
                    logger.error(f"Failed to update existing event {contest['name']} after conflict: {update_err}")
            else:
                logger.error(f"Failed to add {contest['name']}: {e}")
        except Exception as e:
            logger.error(f"Failed to add {contest['name']}: {e}")

    if not args.dry_run:
        save_events(saved)


if __name__ == "__main__":
    main()
