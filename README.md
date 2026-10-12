# Canceled-Listing Lead Uploader

Every day this takes your **Vulcan7 export**, cleans it up, and loads the good leads into
your **Smartlead** campaign. From there, Smartlead sends the emails, and replies flow into
**GoHighLevel**.

```
Vulcan7 export (CSV)  ->  this tool cleans it  ->  Smartlead campaign  ->  replies go to GoHighLevel
```

**What the cleanup does**
- Fixes names and addresses ("JOHN SMITH" becomes "John Smith", "1234 N MAIN ST" becomes "1234 N Main St").
- Removes leads with no email or a broken email.
- Removes leads with no property address, because your emails mention it.
- Removes duplicates, so the same person or the same property isn't loaded twice in one day.
- Skips anyone this tool has **ever** sent to Smartlead before, by checking a record it keeps.
- Companies and trusts get "Homeowner" as their first name. You can change this so they're skipped instead.
- Turns on Smartlead's own safety checks, so Smartlead also refuses anyone who unsubscribed, bounced, is on your block list, or is already in another of your campaigns.

**Test mode is the default.** A normal run only *shows* what would be uploaded. Nothing goes
to Smartlead unless you add `--live` or use the **Run LIVE upload** button.

---

## Where it runs: your Mac Mini

Set this up on the **Mac Mini at home**. It stays on, and it keeps the one master record of who
has already been loaded. If you ran it on both Macs, each one would keep its own record, and
the same people could be loaded twice.

You can still do the Vulcan7 export from your **MacBook Air**. Step 7 shows how to send the file
to the Mac Mini automatically through iCloud Drive.

---

## One-time setup (about 20 minutes, on the Mac Mini)

### Step 1: Open Terminal
Press `Command + Space`, type **Terminal**, and press Return. Terminal is a window where you
type commands. Type (or paste) each command, then press Return.

### Step 2: Copy this project onto the Mac Mini
Paste this into Terminal:
```
cd ~/Documents && git clone https://github.com/Robhaddad12/seller-campaign.git && cd seller-campaign
```
- If a box pops up asking to install **"command line developer tools"**, click **Install**,
  wait for it to finish, then paste the command again. This one install also gives you Python,
  the program this tool runs on.
- GitHub may ask you to sign in. Use your GitHub account.

The project is now in **Documents > seller-campaign**.

Check that Python works:
```
python3 --version
```
You should see something like `Python 3.9` or higher.

### Step 3: Store your Smartlead API key safely
Your API key works like a password to your Smartlead account. It goes in a private file called
`.env` that stays on your Mac only. It is never uploaded to GitHub and never written into the code.

1. In Smartlead, click your profile or **Settings**, then find **API Key** and copy it.
2. In Terminal (make sure you're still in the project folder from Step 2), paste:
   ```
   cp .env.example .env && open -e .env
   ```
   This creates the `.env` file and opens it in TextEdit.
3. Replace `paste_your_key_here` with your key. No spaces and no quotes, like this:
   `SMARTLEAD_API_KEY=abc123yourkey`
4. Save (`Command + S`) and close TextEdit.

> Finder hides files whose names start with a dot, so you won't see `.env` there. That's normal.
> If you ever think the key has leaked, create a new one in Smartlead and paste it into `.env`.

### Step 4: Choose your Smartlead campaign
To see all your campaigns and their numbers:
```
python3 run_daily.py --list-campaigns
```
Then open the settings file:
```
open -e settings.ini
```
Replace `PUT_CAMPAIGN_NUMBER_HERE` with your campaign's number, then save.

### Step 5: Set up your email template in Smartlead
Each lead arrives in Smartlead with these fields, which you can drop into your emails:

| Write this in your Smartlead email | It becomes |
|---|---|
| `{{first_name}}` | John (or "Homeowner" for companies and trusts) |
| `{{last_name}}` | Smith |
| `{{property_address}}` | 1234 N Main St |
| `{{city}}` | Scottsdale |
| `{{state}}` / `{{zip}}` | AZ / 85251 |
| `{{video_url}}` | empty for now; your HeyGen videos go here later |

Example: *"Hi {{first_name}}, I saw your listing at {{property_address}} in {{city}} came off the market…"*

Also put your name, Realty One Group, your license number, your physical address, and an
unsubscribe link at the bottom of every email. Smartlead has an unsubscribe-link option in the
campaign editor.

### Step 6: Try it with the fake test file
```
python3 run_daily.py --file sample/FAKE_vulcan7_export.csv
```
You'll see 7 leads ready and 4 removed, each with its reason. Nothing is uploaded, because this
is test mode.

### Step 7 (optional): Drop files in from your laptop through iCloud Drive
1. On **both** Macs, make sure you're signed into the same Apple ID and iCloud Drive is on.
2. On the MacBook Air, in Finder > iCloud Drive, create a folder called **Vulcan7 Inbox**.
3. On the Mac Mini, open `settings.ini` and change the inbox line to:
   ```
   inbox_folder = ~/Library/Mobile Documents/com~apple~CloudDocs/Vulcan7 Inbox
   ```
Now anything you save into **iCloud Drive > Vulcan7 Inbox** on your laptop shows up on the
Mac Mini within a minute or so.

---

## Every day (3 steps)

1. **Export** your new canceled listings from Vulcan7 as a CSV. Save the file in the inbox
   folder: either **seller-campaign > vulcan7-inbox**, or **iCloud Drive > Vulcan7 Inbox** if you did Step 7.
2. **Preview:** double-click **`Run TEST (preview only).command`** in the project folder.
   Read the summary and check the lists in the `reports` folder.
3. **Upload:** double-click **`Run LIVE upload.command`** and type `YES`.

That's it. Once a file has been uploaded, it's moved into the `processed` folder, so it can never
be loaded twice.

**The first time you double-click** a `.command` file, your Mac may say it "cannot be opened."
Right-click the file, choose **Open**, then click **Open** again. After that, double-clicking works.

If you prefer typing commands in Terminal:
```
cd ~/Documents/seller-campaign
python3 run_daily.py            # preview only (test mode)
python3 run_daily.py --live     # upload for real
```

---

## Where to look afterwards

| Folder | What's in it |
|---|---|
| `reports/` | For each run, a list of the leads that were (or would be) uploaded, plus a list of the leads that were removed and why. Open them in Excel or Numbers. |
| `records/loaded_leads.csv` | Everyone ever sent to Smartlead, with the date. This is how repeats are skipped. **Don't delete it.** |
| `logs/run-log.txt` | A diary of every run. |
| `processed/` | Vulcan7 files that were already uploaded. |

None of these folders are uploaded to GitHub, so your lead data stays on your Mac.

---

## Changing how it works: `settings.ini`

Open it with `open -e settings.ini`. The notes inside explain each line.

- **Owners with several emails:** `emails_per_owner = first` uses only the best email (recommended,
  because fewer bounces protect your warmed-up inboxes). Change it to `all` to email every address.
- **Companies and trusts:** `companies_and_trusts = keep` or `skip`. You can also change the
  word used for their first name (`company_first_name`).
- **Vulcan7 column names:** if Vulcan7 renames a column, the tool stops and lists the column
  names it found. Add the new name to the matching line in the `[columns]` section, after a `|`.

---

## Connecting Smartlead to GoHighLevel (point-and-click, no code)

Replies should land in GoHighLevel as soon as they arrive. Set this up once inside Smartlead.
Menu names move around, so follow what you see on screen:

1. In **Smartlead**, go to **Settings > Integrations** (or **CRM / Webhooks**) and look for
   **GoHighLevel**. If it's there, click **Connect** and sign in to GoHighLevel. Choose
   **"Email Replied"** (and, if offered, "Lead Category Updated" for Interested replies)
   as the events to send.
2. **If GoHighLevel isn't listed,** use a webhook instead:
   - In **GoHighLevel**, go to **Automation > Workflows > Create Workflow**. Choose the trigger
     **Inbound Webhook** and copy the web address it gives you.
   - In **Smartlead**, open the campaign, find **Webhooks > Add Webhook**, paste that address,
     and choose the **Email Replied** event.
   - Back in the GoHighLevel workflow, add these actions: **Create/Update Contact** (map email,
     first name, property address), **Add Tag** `smartlead-replied`,
     **Create Opportunity** in your seller pipeline, and **Send Internal Notification**
     (a text or email to you).
3. **Test it:** add your own email as a lead in a test campaign, reply to the email it sends
   you, and check that you show up in GoHighLevel within a minute.

---

## If something goes wrong

| Message | What to do |
|---|---|
| `No Smartlead API key found` | Redo Step 3. |
| `Smartlead rejected the API key` | The key in `.env` is wrong or old. Copy it again from Smartlead. |
| `Smartlead could not find that campaign` | Check `campaign_id` in `settings.ini` (Step 4). |
| `I found no email column...` | Vulcan7 used a column name the tool doesn't recognize. Add it to `settings.ini` (see above). |
| `could not make a secure connection` | Open Finder > Applications > Python 3.x, double-click **Install Certificates.command**, and try again. |
| `No CSV files in the inbox folder` | Save the export into the inbox folder, as a `.csv` file. |

If an upload stops partway through, just run it again. The leads Smartlead already accepted are
recorded, so no one is loaded twice.

---

## For the curious: what's in this project

- `run_daily.py` is the one command you run.
- `pipeline/clean.py` holds the cleanup rules.
- `pipeline/smartlead.py` handles talking to Smartlead.
- `settings.ini` holds your choices. **This is the only file you normally edit.**
- `.env` holds your secret API key. It lives on your Mac only.
- `sample/FAKE_vulcan7_export.csv` is made-up leads for practice.
- `tests/` contains automatic checks. Run them with `python3 -m unittest discover tests`. They use fake
  leads and a pretend Smartlead, so nothing real is sent.

## Coming next
- Run automatically every morning on the Mac Mini.
- Add the HeyGen video link into `{{video_url}}` for each lead.
