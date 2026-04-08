import json
import os
import logging
import argparse
from datetime import datetime

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
    
    logger.info("Fetching contests...")
    all_contests = (
        fetch_codeforces(days_limit=args.days) +
        fetch_leetcode(days_limit=args.days) +
        fetch_codechef(days_limit=args.days)
    )
    
    logger.info(f"Found {len(all_contests)} total upcoming contests.")

    for c in all_contests:
        color_id = get_platform_color(c['id'])
        event_body = build_event(c['name'], c['url'], c['start'], c['end'], color_id)
        
        if c['id'] in saved:
            event_id = saved[c['id']]
            if args.dry_run:
                logger.info(f"[DRY-RUN] Would update: {c['name']} ({c['start'].strftime('%d %b %H:%M')})")
            else:
                try:
                    service.events().update(
                        calendarId='primary',
                        eventId=event_id,
                        body=event_body
                    ).execute()
                    logger.info(f"Updated: {c['name']} ({c['start'].strftime('%d %b %H:%M')})")
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
                saved[c['id']] = created['id']
                logger.info(f"Added: {c['name']} ({c['start'].strftime('%d %b %H:%M')})")
            except Exception as e:
                logger.error(f"Failed to add {c['name']}: {e}")

    if not args.dry_run:
        save_events(saved)

if __name__ == "__main__":
    main()
