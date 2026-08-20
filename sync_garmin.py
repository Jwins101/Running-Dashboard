"""
Pulls recent running activities from Garmin Connect and writes data.json
in the format the dashboard expects. Run on a schedule via
.github/workflows/sync.yml.

Points GARMINTOKENS at a folder containing a previously-saved
garmin_tokens.json (generated locally via generate_garmin_tokens.py, from
a trusted residential IP). If a valid cached token is present, the
library reuses it instead of doing a fresh password login — fresh logins
from CI IPs get rate-limited / challenged by Garmin.

Env vars:
    GARMIN_TOKEN_DIR   folder containing garmin_tokens.json
    GARMIN_EMAIL       used as fallback / required by the constructor
    GARMIN_PASSWORD    used as fallback / required by the constructor
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

MI = 1609.34
LOOKBACK_DAYS = 210  # keep ~7 months of history in the file


def _first_present(d, paths):
    """Try several possible nested-key paths against a dict and return the
    first one that resolves to a non-None value. Garmin's raw JSON schema
    for sleep/stress isn't fully documented for this library version, so
    this hedges against a couple of plausible shapes instead of assuming
    one and crashing if it's wrong."""
    if not isinstance(d, dict):
        return None
    for path in paths:
        cur = d
        ok = True
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return None


def get_client():
    token_dir = os.environ.get("GARMIN_TOKEN_DIR")
    if token_dir:
        os.environ["GARMINTOKENS"] = os.path.abspath(token_dir)

    from garminconnect import Garmin  # import after GARMINTOKENS is set

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("GARMIN_EMAIL/GARMIN_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    client = Garmin(email, password)
    client.login()
    return client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data.json", help="Output path for the data file")
    args = parser.parse_args()

    client = get_client()

    end = datetime.now()
    start = end - timedelta(days=LOOKBACK_DAYS)
    activities = client.get_activities_by_date(
        start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), activitytype="running"
    )

    # Wellness: steps, sleep score, stress — last 14 days only (keeps the
    # day-over-day chart readable; sleep/stress need one call per day)
    wellness_days = 14
    wellness = []
    steps_start = end - timedelta(days=wellness_days)
    try:
        steps_by_date = {
            d["calendarDate"]: d.get("totalSteps")
            for d in client.get_daily_steps(
                steps_start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            )
        }
    except Exception as e:
        print(f"Could not fetch steps: {e}", file=sys.stderr)
        steps_by_date = {}

    for i in range(wellness_days):
        d = (end - timedelta(days=wellness_days - 1 - i)).strftime("%Y-%m-%d")
        sleep_score = None
        stress_val = None

        try:
            sleep = client.get_sleep_data(d)
            sleep_score = _first_present(
                sleep,
                [
                    ("dailySleepDTO", "sleepScores", "overall", "value"),
                    ("sleepScores", "overall", "value"),
                    ("dailySleepDTO", "sleepScores", "overallScore"),
                    ("overallSleepScore",),
                ],
            )
            if i == 0:
                print(f"[debug] sleep keys for {d}: {list(sleep.keys()) if isinstance(sleep, dict) else type(sleep)}", file=sys.stderr)
        except Exception as e:
            print(f"Could not fetch sleep for {d}: {e}", file=sys.stderr)

        try:
            stress = client.get_stress_data(d)
            stress_val = _first_present(
                stress,
                [
                    ("avgStressLevel",),
                    ("dailyStress", "avgStressLevel"),
                    ("stats", "avgStressLevel"),
                ],
            )
            if i == 0:
                print(f"[debug] stress keys for {d}: {list(stress.keys()) if isinstance(stress, dict) else type(stress)}", file=sys.stderr)
        except Exception as e:
            print(f"Could not fetch stress for {d}: {e}", file=sys.stderr)

        wellness.append(
            {
                "date": d,
                "steps": steps_by_date.get(d),
                "sleep_score": sleep_score,
                "stress": stress_val,
            }
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
        "wellness": wellness,
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f)

    print(f"Wrote {len(runs)} runs to {args.out}")


if __name__ == "__main__":
    main()
