"""
Pulls running activities from Garmin Connect and merges them into a
PERMANENT, ever-growing archive at --out (default data.json). Unlike the
original version of this script, nothing is ever dropped or overwritten
wholesale — new runs are appended, existing ones are left alone, and the
file only grows over time. Run on a schedule via .github/workflows/sync.yml.

First run (no existing archive found): backfills ~13 months of history.
Every run after that: only fetches a short recent window and skips any
activity already present in the archive (matched by Garmin's activity ID).

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

INITIAL_BACKFILL_DAYS = 400   # only used the very first time, no archive exists yet
INCREMENTAL_LOOKBACK_DAYS = 10  # small overlap window on every run after that
WELLNESS_REFRESH_DAYS = 21     # re-check/refresh wellness for the last N days each run

# South Charlotte / Steele Creek (zip 28278) — used when a run has no GPS
# start coordinates (indoor treadmill, GPS lock failure, etc.)
HOME_LAT = 35.102
HOME_LON = -81.025


def _first_present(d, paths):
    """Try several possible nested-key paths against a dict and return the
    first one that resolves to a non-None value. Garmin's raw JSON schema
    isn't fully documented for this library version, so this hedges
    against a couple of plausible shapes instead of assuming one and
    crashing if it's wrong."""
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


def run_signature(r):
    """A fallback identity for a run when Garmin's activity ID isn't
    available (or wasn't captured yet, as with runs saved by the old
    pre-archive version of this script). Two runs on the same date with
    the same distance and pace are treated as the same run."""
    return (r.get("date"), round(r.get("dist_mi") or 0, 2), round(r.get("pace_min_mi") or 0, 2))


def dedupe_runs(runs):
    """Collapse any duplicate runs already sitting in the archive — this
    is what heals a file that got doubled by the id-less migration bug,
    without needing a separate one-off cleanup script.

    Always groups by the date+distance+pace signature FIRST, regardless
    of whether an id is present. The previous version keyed by id when
    available and by signature otherwise — which meant an id-tagged copy
    and a non-id copy of the exact same run never collided, since they
    lived under different keys. Signature is a reliable match either way
    (both copies of a real duplicate are computed from the same source
    activity, so distance/pace round identically), so it's used as the
    single grouping key, with id only used to prefer the richer record."""
    best = {}
    for r in runs:
        sig = run_signature(r)
        existing = best.get(sig)
        if existing is None:
            best[sig] = r
            continue
        r_score = (1 if r.get("id") is not None else 0) + len(r.get("splits") or [])
        e_score = (1 if existing.get("id") is not None else 0) + len(existing.get("splits") or [])
        if r_score > e_score:
            best[sig] = r
    return list(best.values())


def load_archive(path):
    """Load the existing permanent archive, if one exists. Returns a dict
    with 'runs' and 'wellness' lists — empty lists if this is the first
    run ever."""
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            data.setdefault("runs", [])
            data.setdefault("wellness", [])
            before = len(data["runs"])
            data["runs"] = dedupe_runs(data["runs"])
            removed = before - len(data["runs"])
            if removed:
                print(f"Cleaned up {removed} duplicate run(s) found in existing archive")
            return data
        except Exception as e:
            print(f"Could not read existing archive at {path}, starting fresh: {e}", file=sys.stderr)
    return {"runs": [], "wellness": []}


def get_run_splits(client, activity_id):
    """Fetch mile-by-mile (or lap-by-lap) splits for an activity. Tries a
    couple of plausible method names since the exact API surface isn't
    fully confirmed for this library version. Returns an empty list
    (never raises) if nothing usable comes back — a run with no splits
    data is fine, a crashed sync is not."""
    if activity_id is None:
        return []

    raw = None
    for method_name in ("get_activity_splits", "get_activity_split_summaries", "get_activity_typed_splits"):
        method = getattr(client, method_name, None)
        if method is None:
            continue
        try:
            raw = method(activity_id)
            if raw:
                break
        except Exception as e:
            print(f"  {method_name}({activity_id}) failed: {e}", file=sys.stderr)

    lap_list = _first_present(raw, [("lapDTOs",), ("splits",)]) if isinstance(raw, dict) else raw
    if not isinstance(lap_list, list):
        return []

    splits = []
    for lap in lap_list:
        if not isinstance(lap, dict):
            continue
        dist_m = _first_present(lap, [("distance",), ("distanceInMeters",), ("distanceMeters",)])
        dur_s = _first_present(lap, [("duration",), ("elapsedDuration",), ("movingDuration",)])
        hr = _first_present(lap, [("averageHR",), ("avgHR",), ("averageHeartRateInBeatsPerMinute",)])
        if not dist_m or not dur_s or dist_m <= 0 or dur_s <= 0:
            continue
        dist_mi = dist_m / MI
        pace = (dur_s / 60) / dist_mi
        splits.append({
            "dist_mi": round(dist_mi, 2),
            "pace_min_mi": round(pace, 2),
            "avg_hr": round(hr) if hr else None,
        })
    return splits


def get_run_coords(client, activity_id):
    """Try to get the activity's actual GPS start coordinates. Falls back
    to home coordinates (South Charlotte, 28278) if the activity has no
    GPS data, the lookup fails, or the method name doesn't match this
    library version — this fallback is deliberate, not just a crash guard."""
    if activity_id is None:
        return HOME_LAT, HOME_LON, False

    details = None
    for method_name in ("get_activity", "get_activity_details", "get_activity_summary"):
        method = getattr(client, method_name, None)
        if method is None:
            continue
        try:
            details = method(activity_id)
            if details:
                break
        except Exception as e:
            print(f"  {method_name}({activity_id}) failed: {e}", file=sys.stderr)

    lat = _first_present(details, [("summaryDTO", "startLatitude"), ("startLatitude",), ("latitude",)])
    lon = _first_present(details, [("summaryDTO", "startLongitude"), ("startLongitude",), ("longitude",)])

    if lat is not None and lon is not None:
        return lat, lon, True
    return HOME_LAT, HOME_LON, False


def get_temp_for_run(lat, lon, date_str, hour):
    """Look up temperature/humidity for a specific hour via Open-Meteo's
    free historical archive API (no key required). Returns (None, None)
    on any failure rather than raising."""
    try:
        import requests

        resp = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": date_str,
                "end_date": date_str,
                "hourly": "temperature_2m,relative_humidity_2m",
                "temperature_unit": "fahrenheit",
                "timezone": "America/New_York",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        humid = hourly.get("relative_humidity_2m", [])
        target = f"{date_str}T{hour:02d}:00"
        if target in times:
            idx = times.index(target)
            t = temps[idx] if idx < len(temps) else None
            h = humid[idx] if idx < len(humid) else None
            return t, h
    except Exception as e:
        print(f"  weather lookup failed for {date_str} {hour}:00: {e}", file=sys.stderr)
    return None, None


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
    parser.add_argument("--out", default="data.json", help="Path to the permanent archive file")
    args = parser.parse_args()

    archive = load_archive(args.out)
    existing_ids = {r["id"] for r in archive["runs"] if r.get("id") is not None}
    existing_signatures = {run_signature(r) for r in archive["runs"]}
    is_first_run = len(archive["runs"]) == 0

    client = get_client()
    end = datetime.now()

    if is_first_run:
        lookback_days = INITIAL_BACKFILL_DAYS
    else:
        # Always cover at least year-to-date, even on routine incremental
        # syncs — this is what keeps "miles this year" on the landing page
        # accurate without needing a special case. Already-archived runs
        # in that range are skipped via the ID check below, so this costs
        # one slightly-larger listing call, not extra per-run enrichment.
        jan_1 = datetime(end.year, 1, 1)
        days_since_jan_1 = (end - jan_1).days + 1
        lookback_days = max(INCREMENTAL_LOOKBACK_DAYS, days_since_jan_1)

    start = end - timedelta(days=lookback_days)

    print(f"{'First-ever run: backfilling' if is_first_run else 'Incremental sync: checking'} "
          f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")

    activities = client.get_activities_by_date(
        start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), activitytype="running"
    )

    new_runs = []
    for a in activities:
        activity_id = _first_present(a, [("activityId",), ("id",)])

        dist_m = a.get("distance") or 0
        dur_s = a.get("duration") or 0
        if dist_m <= 0 or dur_s <= 0:
            continue
        dist_mi = dist_m / MI
        pace = (dur_s / 60) / dist_mi
        start_time_full = a.get("startTimeLocal", "")  # e.g. "2026-08-19 19:52:58"
        start_date = start_time_full[:10]

        sig = (start_date, round(dist_mi, 2), round(pace, 2))
        if (activity_id is not None and activity_id in existing_ids) or sig in existing_signatures:
            continue  # already archived, nothing to do — checked both ways since
            # older archive entries (pre-permanent-archive) have no ID at all

        record = {
            "id": activity_id,
            "date": start_date,
            "dist_mi": round(dist_mi, 2),
            "pace_min_mi": round(pace, 2),
            "avg_hr": a.get("averageHR"),
        }

        # Every genuinely new run gets full enrichment — splits, GPS, weather.
        # This used to be capped to a recent window because it ran on the
        # WHOLE history every day; now it only ever runs once per run, ever.
        record["splits"] = get_run_splits(client, activity_id)

        lat, lon, used_gps = get_run_coords(client, activity_id)
        try:
            hour = int(start_time_full[11:13]) if len(start_time_full) >= 13 else 12
        except ValueError:
            hour = 12
        temp_f, humidity = get_temp_for_run(lat, lon, start_date, hour)
        record["time"] = start_time_full[11:16] if len(start_time_full) >= 16 else None
        record["temp_f"] = temp_f
        record["humidity"] = humidity
        record["used_gps"] = used_gps

        new_runs.append(record)
        if activity_id is not None:
            existing_ids.add(activity_id)
        existing_signatures.add(sig)

    archive["runs"].extend(new_runs)
    archive["runs"].sort(key=lambda r: r["date"])
    print(f"Added {len(new_runs)} new run(s). Archive now has {len(archive['runs'])} total.")

    # Wellness: steps, sleep score, stress. Merged by date so history is
    # never lost — only the last WELLNESS_REFRESH_DAYS days get re-checked
    # each run (covers newly-finalized data), everything older stays as-is.
    wellness_by_date = {w["date"]: w for w in archive["wellness"] if w.get("date")}

    refresh_days = WELLNESS_REFRESH_DAYS
    steps_start = end - timedelta(days=refresh_days)
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

    for i in range(refresh_days):
        d = (end - timedelta(days=refresh_days - 1 - i)).strftime("%Y-%m-%d")
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
        except Exception as e:
            print(f"Could not fetch stress for {d}: {e}", file=sys.stderr)

        wellness_by_date[d] = {
            "date": d,
            "steps": steps_by_date.get(d),
            "sleep_score": sleep_score,
            "stress": stress_val,
        }

    archive["wellness"] = sorted(wellness_by_date.values(), key=lambda w: w["date"])
    archive["generated_at"] = datetime.utcnow().isoformat() + "Z"

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(archive, f)

    print(f"Wrote archive: {len(archive['runs'])} runs, {len(archive['wellness'])} wellness days -> {args.out}")


if __name__ == "__main__":
    main()
