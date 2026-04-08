import requests
from datetime import datetime

def fetch_codeforces_contests():
    url = "https://codeforces.com/api/contest.list"
    
    response = requests.get(url)
    data = response.json()

    if data['status'] != 'OK':
        print("Error fetching data")
        return []

    contests = data['result']

    upcoming = []

    for contest in contests:
        if contest['phase'] == 'BEFORE':
            name = contest['name']
            start_time = datetime.fromtimestamp(contest['startTimeSeconds'])
            duration = contest['durationSeconds'] // 60  # in minutes

            upcoming.append({
                'name': name,
                'start_time': start_time,
                'duration': duration
            })

    return upcoming


if __name__ == "__main__":
    contests = fetch_codeforces_contests()

    print("\nUpcoming Codeforces Contests:\n")
    for c in contests[:5]:  # show top 5
        print(f"{c['name']}")
        print(f"Start: {c['start_time']}")
        print(f"Duration: {c['duration']} minutes")
        print("-" * 40)