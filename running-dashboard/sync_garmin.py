"""
Pulls recent running activities from Garmin Connect and writes data.json
in the format the dashboard expects. Meant to be run on a schedule
(see .github/workflows/sync.yml) so the hosted dashboard stays current.

Requires env vars: GARMIN_EMAIL, GARMIN_PASSWORD
Install: pip install garminconnect
"""
import json
import os
import sys
from datetime import datetime, timedelta

from garminconnect import Garmin

MI = 1609.34
LOOKBACK_DAYS = 210  # keep ~7 months of history in the file


def main():
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("Missing GARMIN_EMAIL / GARMIN_PASSWORD env vars", file=sys.stderr)
        sys.exit(1)

    client = Garmin(email, password)
    client.login()

    end = datetime.now()
    start = end - timedelta(days=LOOKBACK_DAYS)
    activities = client.get_activities_by_date(
        start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), activitytype="running"
    )

    runs = []
    for a in activities:
        dist_m = a.get("distance") or 0
        dur_s = a.get("duration") or 0
        if dist_m <= 0 or dur_s <= 0:
            continue
        dist_mi = dist_m / MI
        pace = (dur_s / 60) / dist_mi
        start_time = a.get("startTimeLocal", "")[:10]
        runs.append(
            {
                "date": start_time,
                "dist_mi": round(dist_mi, 2),
                "pace_min_mi": round(pace, 2),
                "avg_hr": a.get("averageHR"),
            }
        )

    runs.sort(key=lambda r: r["date"])

    out = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "runs": runs,
    }

    with open("data.json", "w") as f:
        json.dump(out, f)

    print(f"Wrote {len(runs)} runs to data.json")


if __name__ == "__main__":
    main()
