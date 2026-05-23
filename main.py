import json
import os
import logging
import argparse
import hashlib
from datetime import datetime, timezone
from googleapiclient.errors import HttpError

from scrapers import fetch_codeforces, fetch_leetcode, fetch_codechef
from calendar_client import authenticate, get_calendar_service, build_event

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('sync.log')
    ]
)
logger = logging.getLogger(__name__)

DATA_FILE = "data/events.json"

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
    Since 'f' is within 'v', this is 100% compliant.
    """
    return hashlib.md5(contest_id.encode('utf-8')).hexdigest()

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
            # Legacy format: "contest_id": "event_id"
            event_id = value
            # Fetch from calendar to get end time and verify existence
            try:
                event = service.events().get(calendarId='primary', eventId=event_id).execute()
                end_time_str = event.get('end', {}).get('dateTime') or event.get('end', {}).get('date')
                changed = True
            except Exception as e:
                # If it doesn't exist or we can't fetch it, remove it
                logger.info(f"Removing legacy event {contest_id} ({event_id}) because it could not be fetched: {e}")
                changed = True
                continue
        elif isinstance(value, dict):
            # New format: "contest_id": {"event_id": "...", "end": "..."}
            event_id = value.get("event_id")
            end_time_str = value.get("end")
        
        if not event_id or not end_time_str:
            changed = True
            continue

        try:
            # Parse the end time.
            if end_time_str.endswith('Z'):
                end_time_str_parsed = end_time_str[:-1] + '+00:00'
            else:
                end_time_str_parsed = end_time_str
            end_dt = datetime.fromisoformat(end_time_str_parsed)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            
            if end_dt < now:
                logger.info(f"Clearing past event: {contest_id} (ended at {end_time_str})")
                changed = True
                continue
            else:
                updated_saved[contest_id] = {
                    "event_id": event_id,
                    "end": end_time_str
                }
        except Exception as e:
            logger.warning(f"Failed to parse end time '{end_time_str}' for {contest_id}, removing: {e}")
            changed = True
            continue

    return updated_saved, changed

def get_platform_color(contest_id):
    """Get color ID based on the platform."""
    if contest_id.startswith('cf_'):
        return '3'   # Blueberry (Codeforces)
    if contest_id.startswith('lc_'):
        return '5'   # Banana (LeetCode)
    if contest_id.startswith('cc_'):
        return '7'  # Tomato (CodeChef)
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
    
    # Clean up and normalize saved events
    logger.info("Cleaning up and normalizing saved events...")
    saved, cleanup_changed = cleanup_saved_events(saved, service)
    
    logger.info("Fetching contests...")
    all_contests = (
        fetch_codeforces(days_limit=args.days) +
        fetch_leetcode(days_limit=args.days) +
        fetch_codechef(days_limit=args.days)
    )
    
    logger.info(f"Found {len(all_contests)} total upcoming contests.")

    for c in all_contests:
        color_id = get_platform_color(c['id'])
        
        # Check if we already have a saved event ID for this contest
        if c['id'] in saved:
            if isinstance(saved[c['id']], dict):
                event_id = saved[c['id']]['event_id']
            else:
                event_id = saved[c['id']]
        else:
            # Generate deterministic ID
            event_id = generate_google_event_id(c['id'])

        event_body = build_event(c['name'], c['url'], c['start'], c['end'], color_id)
        event_body['id'] = event_id
        
        if c['id'] in saved:
            if args.dry_run:
                logger.info(f"[DRY-RUN] Would update: {c['name']} ({c['start'].strftime('%d %b %H:%M')})")
            else:
                try:
                    service.events().update(
                        calendarId='primary',
                        eventId=event_id,
                        body=event_body
                    ).execute()
                    saved[c['id']] = {
                        "event_id": event_id,
                        "end": c['end'].isoformat()
                    }
                    logger.info(f"Updated: {c['name']} ({c['start'].strftime('%d %b %H:%M')})")
                except HttpError as e:
                    if e.resp.status == 404:
                        logger.info(f"Event {event_id} not found in calendar (may have been deleted). Re-inserting...")
                        try:
                            # Re-insert using deterministic ID
                            det_id = generate_google_event_id(c['id'])
                            event_body['id'] = det_id
                            created = service.events().insert(
                                calendarId='primary',
                                body=event_body
                            ).execute()
                            saved[c['id']] = {
                                "event_id": det_id,
                                "end": c['end'].isoformat()
                            }
                            logger.info(f"Re-inserted: {c['name']} ({c['start'].strftime('%d %b %H:%M')})")
                        except Exception as insert_err:
                            logger.error(f"Failed to re-insert {c['name']}: {insert_err}")
                    else:
                        logger.error(f"Failed to update {c['name']}: {e}")
                except Exception as e:
                    logger.error(f"Failed to update {c['name']}: {e}")
            continue

        if args.dry_run:
            logger.info(f"[DRY-RUN] Would add: {c['name']} ({c['start'].strftime('%d %b %H:%M')})")
        else:
            try:
                created = service.events().insert(
                    calendarId='primary',
                    body=event_body
                ).execute()
                saved[c['id']] = {
                    "event_id": created['id'],
                    "end": c['end'].isoformat()
                }
                logger.info(f"Added: {c['name']} ({c['start'].strftime('%d %b %H:%M')})")
            except HttpError as e:
                if e.resp.status == 409:
                    # 409 Conflict: Event already exists on Google Calendar (e.g. from an out-of-sync run)
                    logger.info(f"Event for {c['name']} already exists on Google Calendar (409 Conflict). Updating it...")
                    try:
                        service.events().update(
                            calendarId='primary',
                            eventId=event_id,
                            body=event_body
                        ).execute()
                        saved[c['id']] = {
                            "event_id": event_id,
                            "end": c['end'].isoformat()
                        }
                        logger.info(f"Updated (resolved conflict): {c['name']} ({c['start'].strftime('%d %b %H:%M')})")
                    except Exception as update_err:
                        logger.error(f"Failed to update existing event {c['name']} after conflict: {update_err}")
                else:
                    logger.error(f"Failed to add {c['name']}: {e}")
            except Exception as e:
                logger.error(f"Failed to add {c['name']}: {e}")

    if not args.dry_run:
        save_events(saved)

if __name__ == "__main__":
    main()
