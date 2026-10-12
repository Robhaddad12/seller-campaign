#!/usr/bin/env python3
"""Daily lead upload: Vulcan7 CSV -> clean -> Smartlead.

    python3 run_daily.py                  TEST MODE (default): shows what would upload, uploads nothing
    python3 run_daily.py --live           uploads for real
    python3 run_daily.py --campaign 123   use a different campaign this one time
    python3 run_daily.py --file x.csv     use one specific file instead of the inbox folder
    python3 run_daily.py --list-campaigns show your Smartlead campaigns and their numbers
"""

import argparse
import csv
import datetime
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pipeline import clean, smartlead  # noqa: E402

RECORD_FILE = os.path.join(HERE, "records", "loaded_leads.csv")
RECORD_FIELDS = ["date_loaded", "email", "first_name", "last_name", "property_address", "city", "campaign_id"]
REPORT_FIELDS = ["first_name", "last_name", "email", "property_address", "city", "state", "zip",
                 "is_company_or_trust", "source_file", "source_row"]
REMOVED_FIELDS = ["reason", "owner", "email", "property_address", "file", "row"]

log_lines = []


def say(text=""):
    print(text)
    log_lines.append(text)


def load_env():
    """Reads KEY=value lines from .env into the environment (without overriding)."""
    path = os.path.join(HERE, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api_key_or_stop():
    key = os.environ.get("SMARTLEAD_API_KEY", "")
    if not key or key == "paste_your_key_here":
        raise SystemExit("STOPPED: No Smartlead API key found. Follow 'Step 3' in the README to create your .env file.")
    return key


def read_record():
    if not os.path.exists(RECORD_FILE):
        return {}
    with open(RECORD_FILE, newline="", encoding="utf-8") as f:
        return {r["email"]: r["date_loaded"] for r in csv.DictReader(f)}


def add_to_record(leads, campaign_id, today):
    os.makedirs(os.path.dirname(RECORD_FILE), exist_ok=True)
    new_file = not os.path.exists(RECORD_FILE)
    with open(RECORD_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RECORD_FIELDS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for lead in leads:
            w.writerow(dict(lead, date_loaded=today, campaign_id=campaign_id))


def write_csv(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def find_files(settings, one_file):
    if one_file:
        return [os.path.abspath(os.path.expanduser(one_file))]
    inbox = os.path.expanduser(settings["inbox_folder"])
    if not os.path.isabs(inbox):
        inbox = os.path.join(HERE, inbox)
    if not os.path.isdir(inbox):
        raise SystemExit("STOPPED: The inbox folder doesn't exist: %s" % inbox)
    names = sorted(n for n in os.listdir(inbox) if n.lower().endswith(".csv"))
    return [os.path.join(inbox, n) for n in names]


def read_files(paths, settings):
    loaded = []
    for path in paths:
        name = os.path.basename(path)
        headers, rows = clean.read_csv(path)
        cols, emails = clean.match_columns(headers, settings["columns"])
        say("File: %s  (%d rows)" % (name, len(rows)))
        for field in ("first_name", "last_name", "full_name", "property_address", "city", "state", "zip"):
            say("   %-17s <- %s" % (field, cols[field] or "(not found)"))
        say("   %-17s <- %s" % ("emails", ", ".join(emails) or "(not found)"))
        problems = []
        if not emails:
            problems.append("no email column")
        if not cols["property_address"]:
            problems.append("no property address column")
        if not (cols["first_name"] or cols["full_name"]):
            problems.append("no owner name column")
        if problems:
            raise SystemExit(
                "STOPPED: In %s I found %s.\nThe column headings in that file are:\n   %s\n"
                "Add the right heading to the [columns] section of settings.ini and run again."
                % (name, " and ".join(problems), "\n   ".join(headers)))
        loaded.append((name, headers, rows, cols, emails))
    return loaded


def main():
    parser = argparse.ArgumentParser(description="Clean Vulcan7 leads and load them into Smartlead.")
    parser.add_argument("--live", action="store_true", help="upload for real (default is test mode)")
    parser.add_argument("--campaign", help="Smartlead campaign number to use this time")
    parser.add_argument("--file", help="a specific CSV file instead of the inbox folder")
    parser.add_argument("--list-campaigns", action="store_true", help="show your Smartlead campaigns")
    args = parser.parse_args()

    load_env()
    settings = clean.load_settings(os.path.join(HERE, "settings.ini"))
    now = datetime.datetime.now()
    today = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%Y-%m-%d_%H%M")

    if args.list_campaigns:
        for c in smartlead.list_campaigns(api_key_or_stop()):
            print("%-10s %-10s %s" % (c.get("id"), c.get("status", ""), c.get("name", "")))
        return 0

    mode = "LIVE" if args.live else "TEST"
    say("=" * 60)
    say("%s   %s MODE%s" % (now.strftime("%Y-%m-%d %I:%M %p"), mode,
                            "" if args.live else " (nothing will be uploaded)"))
    say("=" * 60)

    campaign_id = (args.campaign or settings["campaign_id"]).strip()
    paths = find_files(settings, args.file)
    if not paths:
        say("No CSV files in the inbox folder. Nothing to do today.")
        return 0

    files = read_files(paths, settings)
    already = read_record()
    leads, removed = clean.scrub(files, settings, already)

    total_rows = sum(len(f[2]) for f in files)
    say("")
    say("Rows read:          %d" % total_rows)
    say("Ready to upload:    %d" % len(leads))
    say("Removed:            %d" % len(removed))
    reasons = {}
    for r in removed:
        key = r["reason"].split(":")[0] if r["reason"].startswith("Email address not valid") else r["reason"]
        key = "Already sent to Smartlead before" if key.startswith("Already sent") else key
        reasons[key] = reasons.get(key, 0) + 1
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        say("   %4d  %s" % (count, reason))

    reports = os.path.join(HERE, "reports")
    ready_file = os.path.join(reports, "%s_%s.csv" % (stamp, "uploaded" if args.live else "PREVIEW_would_upload"))
    removed_file = os.path.join(reports, "%s_removed.csv" % stamp)
    write_csv(ready_file, REPORT_FIELDS, leads)
    write_csv(removed_file, REMOVED_FIELDS, removed)

    if leads:
        say("")
        say("First %d leads:" % min(10, len(leads)))
        for l in leads[:10]:
            say("   %-12s %-14s %-32s %s, %s" % (l["first_name"], l["last_name"], l["email"],
                                                 l["property_address"], l["city"]))
    say("")
    say("Full list:      reports/%s" % os.path.basename(ready_file))
    say("Removed list:   reports/%s" % os.path.basename(removed_file))

    if not args.live:
        say("")
        say("TEST MODE: nothing was uploaded and nothing was recorded.")
        say("When the lists look right, run:  python3 run_daily.py --live")
        return 0

    # ---------------- live upload ----------------
    key = api_key_or_stop()
    if not campaign_id.isdigit():
        raise SystemExit("STOPPED: Put your Smartlead campaign number in settings.ini (campaign_id).")
    campaign = smartlead.get_campaign(key, campaign_id)
    say("")
    say("Uploading to Smartlead campaign %s: %s" % (campaign_id, campaign.get("name", "")))

    uploaded = 0
    for start in range(0, len(leads), smartlead.BATCH_SIZE):
        batch = leads[start:start + smartlead.BATCH_SIZE]
        result = smartlead.upload_batch(key, campaign_id, batch)
        add_to_record(batch, campaign_id, today)  # only after Smartlead accepted the batch
        uploaded += len(batch)
        say("   Sent %d leads. Smartlead says: added %s, already in this campaign %s, "
            "blocked/unsubscribed %s, invalid %s, in another campaign %s" % (
                len(batch), result.get("upload_count", "?"), result.get("already_added_to_campaign", "?"),
                result.get("unsubscribed_leads", result.get("block_count", "?")),
                result.get("invalid_email_count", "?"), result.get("duplicate_count", "?")))

    if not args.file:
        done = os.path.join(HERE, "processed")
        os.makedirs(done, exist_ok=True)
        for p in paths:
            shutil.move(p, os.path.join(done, "%s_%s" % (stamp, os.path.basename(p))))
        say("Moved today's file(s) to the 'processed' folder.")
    say("DONE: %d leads sent to Smartlead." % uploaded)
    return 0


def save_log():
    os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
    with open(os.path.join(HERE, "logs", "run-log.txt"), "a", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n\n")


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    except SystemExit as e:
        if isinstance(e.code, str):
            say(e.code)
            code = 1
        else:
            code = e.code or 0
    except smartlead.SmartleadError as e:
        say("STOPPED: %s" % e)
        say("Leads already accepted by Smartlead were recorded, so running again is safe.")
    except Exception as e:  # anything unexpected still lands in the log
        say("STOPPED: Unexpected problem: %r" % e)
    finally:
        if log_lines:
            save_log()
    sys.exit(code)
