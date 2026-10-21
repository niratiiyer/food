# Step-by-step guide: from zero to a live app with real users

This guide assumes you've never deployed a web app before. Do the parts in order.
Each step says **what to do** and **how to tell it worked**.

- Part 1: Install the tools (about 30 minutes, once)
- Part 2: Run the app on your own computer
- Part 3: Try it out as a host and as a student
- Part 4: Put it on the internet with Render
- Part 5: Optional: email alerts (off by default)
- Part 6: Get real users and track usage
- Part 7: What to build next
- Part 8: How to talk about it in interviews

---

## Part 1: Install the tools

You need four things. If you already have one, skip it.

### 1a. A code editor
Install **VS Code**: https://code.visualstudio.com. This is where you'll read and edit the code.

### 1b. Git (tracks changes to your code and uploads it to GitHub)
- **Mac:** open the **Terminal** app (press Cmd+Space, type "Terminal"), type `git --version` and press Enter. If it asks to install developer tools, click Install.
- **Windows:** download from https://git-scm.com/download/win and click through the installer with the default options. Afterwards use the **Git Bash** app as your terminal for every command in this guide.

Worked if: `git --version` prints something like `git version 2.x`.

### 1c. Python 3.12 or newer
- Download from https://www.python.org/downloads/ and run the installer.
- **Windows:** on the first installer screen, tick **"Add python.exe to PATH"**.

Worked if: `python3 --version` (Mac) or `python --version` (Windows) prints `Python 3.12` or higher.
On Windows, type `python` wherever this guide says `python3`.

### 1d. Postgres (the database)
- **Mac:** install **Postgres.app** from https://postgresapp.com, open it, and click **Initialize**. Then follow the "Configure your $PATH" step on their site so the `psql` command works.
- **Windows:** download the installer from https://www.postgresql.org/download/windows/. When it asks for a password for the `postgres` user, type `postgres` (fine for your own computer only). Keep the port as 5432.

Worked if: `psql --version` prints a version number.

---

## Part 2: Run the app on your computer

### 2a. Download the code
In your terminal:
```bash
git clone https://github.com/niratiiyer/food.git
cd food
```
`cd food` means "move into the food folder". Every command from here on runs inside that folder.

### 2b. Create the two databases
One database for the app and one that the automated tests wipe and refill.

- **Mac (Postgres.app):**
  ```bash
  createdb leftover
  createdb leftover_test
  ```
- **Windows:**
  ```bash
  psql -U postgres -c "CREATE DATABASE leftover;"
  psql -U postgres -c "CREATE DATABASE leftover_test;"
  ```
  (Type the password `postgres` if asked.)

Note: `createdb` prints **nothing** when it works. That silence is success, not a problem.

Worked if: `psql -l` (Mac) or `psql -U postgres -l` (Windows) shows a table that includes `leftover` and `leftover_test`. Press `q` to get out of the list if it doesn't return to the prompt.

### 2c. Make a private Python environment and install the libraries
```bash
python3 -m venv .venv
```
Then switch it on. You'll need to repeat this line every time you open a new terminal:
- **Mac:** `source .venv/bin/activate`
- **Windows (Git Bash):** `source .venv/Scripts/activate`

You'll see `(.venv)` at the start of your prompt. Now install:
```bash
pip install -r requirements-dev.txt
```

### 2d. Create your settings file
```bash
cp .env.example .env
```
Open `.env` in VS Code and change two things:
1. `SECRET_KEY=`: run `python3 -c "import secrets; print(secrets.token_hex(32))"`, copy the output, and paste it after the `=`.
2. **Mac only:** Postgres.app logs you in as your Mac user, not as `postgres`. Change the database line to:
   `DATABASE_URL=postgresql://localhost:5432/leftover`

### 2e. Start the app
```bash
uvicorn app.main:app --reload --env-file .env
```
Worked if: you see `Uvicorn running on http://127.0.0.1:8000`. Open http://localhost:8000 in your browser.
To stop the app, press Ctrl+C in the terminal. `--reload` restarts it automatically whenever you save a code file.

### 2f. Run the tests
Open a **second** terminal window, `cd` into the folder, activate `.venv` again (step 2c), then:
- **Windows:** `pytest`
- **Mac:** `TEST_DATABASE_URL=postgresql://localhost:5432/leftover_test pytest`

Worked if: it ends with `10 passed`. One of the tests has 30 fake students claim the last 2 portions at the same instant, and checks that exactly 2 succeed.

---

## Part 3: Try it out

1. Go to http://localhost:8000/signup. Make an account, tick **"I run events…"**, and you're a **host**.
2. Fill in the form and click **Post food**.
3. The listing now shows on the home page. Email alerts are off, so students find food by checking the site (see Part 5 if you ever want emails).
4. Open a **private/incognito window** (so you're logged out), sign up as a student without ticking the box, and click **Claim one**. You get a pickup code.
5. Back in the host window, refresh **Post food**. You'll see the student and their code. Click **Picked up**.
6. Visit http://localhost:8000/stats to see the impact numbers.

---

## Part 4: Put it on the internet (Render)

### 4a. Name your branch `main`
The code is already in your GitHub repo `niratiiyer/food`. Make sure its branch is called `main`:
1. Go to https://github.com/niratiiyer/food/branches.
2. If the only branch isn't called `main`, click the **⋯** menu (or the pencil icon) next to it → **Rename branch**, type `main`, and confirm.
3. Open GitHub Desktop. If it says the branch was renamed, click the button to switch to `main`.

### 4b. Create the app on Render
1. Sign up at https://render.com with your GitHub account.
2. Click **New** → **Blueprint**.
3. Pick the `food` repo. Render reads the `render.yaml` file and plans to create a web service called `leftover` and a database called `leftover-db`.
4. It asks you to fill in the settings marked `sync: false`:
   - `ALLOWED_EMAIL_DOMAIN`: your school's email domain, e.g. `yourschool.edu`. Only those emails can sign up.
   - `BASE_URL`: leave it blank for now.
   - `RESEND_API_KEY`, `EMAIL_FROM`: leave them blank. They're only for the optional email alerts in Part 5.
5. Click **Apply**. The first build takes a few minutes.
6. When it's done, open the `leftover` service. Its URL is at the top, something like `https://leftover-xxxx.onrender.com`. Copy it, go to **Environment**, set `BASE_URL` to it, and save. The app redeploys.

Worked if: the URL shows your app, and `<your URL>/healthz` shows `{"ok":true}`.

From now on, **every time you merge into main, Render redeploys automatically.**

### 4c. Know the free-tier limits
- **The free web service sleeps after 15 minutes with no visitors.** The next visitor waits about a minute while it wakes up. That's fine for testing. Before a real launch, either upgrade to the cheapest paid instance or accept the delay.
- **The free Postgres database expires after 30 days.** After a 14-day grace period, Render **deletes it along with all your data.** Before real students use the app, do one of these:
  - upgrade the database to Render's cheapest paid plan (a few dollars a month), or
  - use a free Postgres from another provider such as Neon (https://neon.tech): create a database there, copy its connection string, and paste it into the `DATABASE_URL` setting on Render.
- **Free Render services can't send email over SMTP** (ports 25, 465 and 587 are blocked). That's why the optional email alerts use Resend's web API instead (Part 5).

---

## Part 5: Optional: email alerts (off by default)

The app works without email: students check the site to see what's available. Alerts are switched off because emailing every student needs a paid domain (about $10/year). If you ever want them, follow these steps, then set `EMAIL_ALERTS` to `on` in Render's Environment settings.

1. Sign up at https://resend.com (it has a free plan).
2. Go to **API Keys** → **Create API Key**. Copy the key (it starts with `re_`).
3. On Render → `leftover` → **Environment**, set `RESEND_API_KEY` to that key.
4. **Sending to other people needs a domain you own.** Until then, Resend only lets you email *your own* address from `onboarding@resend.dev`. That's good for testing: set `EMAIL_FROM` to `Leftover <onboarding@resend.dev>`.
5. For real users, buy a cheap domain (around $10/year), add it in Resend under **Domains**, and add the DNS records Resend shows you at the place you bought the domain. Once Resend shows it as verified, set `EMAIL_FROM` to something like `Leftover <alerts@yourdomain.com>`.

Worked if: you post food as a host, and the student account (using your own email) receives the alert.

**Text messages:** leave these for later, as you planned. Every text costs money (Twilio and similar services charge per message). When you add them, add a new sending function next to `send_email` in `app/notify.py` and a phone-number field on the user.

---

## Part 6: Get real users and track usage

The app is just a tool. The users come from your nonprofit work.

1. **Start with 2–3 friendly hosts**: clubs that regularly over-order, or a dining hall manager. Sign them up yourself, sitting next to them, and show them the **Post food** page. It takes 30 seconds to post.
2. **Recruit students where food insecurity is already discussed**: your nonprofit's mailing list, the campus food pantry, residence hall group chats.
3. **Check food-safety rules first.** Ask your dining services or student activities office about rules for redistributing leftover food. Many campuses already have a policy. Add any required notes, like an allergen warning, to the host form.
4. **Watch the numbers** at `/stats`: meals rescued, students fed, hosts. Screenshot them every week. A chart of real growth beats any demo.
5. **Ask for feedback.** Check in with a host after their first post and a student after their first pickup. Real fixes from real feedback make great interview stories.

---

## Part 7: What to build next (in rough order)

1. **Waitlist.** When a listing is full, let students join a queue. When a hold expires, give the portion to the first person in line and email them. The locking pattern in `claim_portion` already shows how to do this safely.
2. **Host approval.** Right now anyone can tick "I'm a host". Add an admin flag and an approval step.
3. **Database migrations with Alembic.** The app creates tables on startup but can't *change* existing ones. Once you have real data, use Alembic (https://alembic.sqlalchemy.org) for any table change.
4. **Rate limiting and password reset.**
5. **Text or email alerts** (both cost money; email is already built in, see Part 5).
6. **Better priority rules.** Let students pick the locations they care about, and only alert them for those.

---

## Part 8: How to talk about it in interviews

Have these ready:

- **The problem:** "Clubs throw away food after events while students on the same campus skip meals. It grew out of the food-insecurity nonprofit I started."
- **The numbers:** "X meals rescued, Y students, Z hosts, over N weeks." (from `/stats`)
- **The hard part:** "When 30 students tap Claim on the last 2 slices at the same moment, a naive version hands out more slices than exist. I wrote a test that proves this: without the lock, 4 students got 2 slices. The fix: each claim runs in a database transaction that first locks the listing's row with `SELECT ... FOR UPDATE`, so claims on one listing run one at a time. A unique index in Postgres is the backstop. Claims are holds that expire after 15 minutes, so no-shows don't waste food."
- **A tradeoff:** "I kept it free to run: no SMS or email at launch, because both cost money per message. Email alerts are built in behind an on/off switch, with a fewest-recent-pickups-first rule so the fastest clickers don't take everything."

Know `app/claims.py` well enough to explain it line by line on a whiteboard.
