# Deploying Leftover to Azure (step by step)

This puts the app on Azure, which Assurant lists in their job post. When you're done you'll have:

```
Your browser
   │
   ▼
leftover-web   (Azure Container App: nginx serving the React dashboard)
   │  /api/* requests are passed through to ↓
   ▼
leftover-api   (Azure Container App: the FastAPI backend + main site)
   │
   ▼
Neon Postgres  (the free database you already made)
```

GitHub Actions builds the two Docker images on every push to `main` and publishes them to GitHub's
free image storage (GitHub Container Registry, `ghcr.io`). Azure downloads them from there.

Time needed: about 45 minutes the first time.

---

## Part 1: Get an Azure account

1. Go to https://azure.microsoft.com/free/students and click **Start free**.
2. Sign in with your **school email**. Azure for Students verifies you're a student and gives you free credit
   without a credit card (check the page for the current amount).
3. When it finishes, you land in the **Azure Portal** (https://portal.azure.com). This is where you'll do everything below.

## Part 2: Set a budget alert (so you never get surprised)

1. In the search bar at the top of the portal, type **Subscriptions** and click it.
2. Click your subscription (usually **Azure for Students**).
3. In the left menu, under **Cost Management**, click **Budgets**, then **+ Add**.
4. Fill in:
   - **Name:** `leftover-budget`
   - **Reset period:** Monthly
   - **Amount:** `5`
5. Click **Next**. Under **Alert conditions**, add three rows:
   - Type **Actual**, % of budget **50**
   - Type **Actual**, % of budget **100**
   - Type **Forecasted**, % of budget **100**
6. Under **Alert recipients (email)**, type your email. Click **Create**.

You'll now get an email if spending heads toward $5. A small app like this normally stays within
Azure Container Apps' free monthly allowance.

## Part 3: Make the Docker images downloadable

1. Push the code to `main` (already done if you're reading this on GitHub). Then go to
   https://github.com/niratiiyer/food/actions and wait for the newest **CI** run to show a green ✓.
   It builds and publishes the images.
2. Go to https://github.com/niratiiyer?tab=packages. You should see **leftover-backend** and **leftover-frontend**.
3. Click **leftover-backend** → **Package settings** (right side, near the bottom) → scroll to **Danger Zone**
   → **Change visibility** → **Public** → type the name to confirm.
4. Do the same for **leftover-frontend**.

Making them public lets Azure download them without a password. Anyone could download the images,
which contain the app's code, but **not** your secrets: those live only in Azure's settings.

## Part 4: Create the backend (leftover-api)

1. In the portal's search bar, type **Container Apps** and click it. Click **+ Create** → **Container App**.

2. **Basics** tab:
   - **Subscription:** Azure for Students
   - **Resource group:** click **Create new**, type `leftover-rg`, click **OK**. (A resource group is a folder for everything this project uses.)
   - **Container app name:** `leftover-api`
   - **Deployment source:** Container image
   - **Region:** the one closest to your Neon database (e.g. **East US** if Neon is in AWS US East)
   - **Container Apps environment:** click **Create new**, name it `leftover-env`, leave the rest, click **Create**.
   - Click **Next: Container**.

3. **Container** tab:
   - **Untick** "Use quickstart image".
   - **Name:** `leftover-api`
   - **Image source:** Docker Hub or other registries
   - **Image type:** Public
   - **Registry login server:** `ghcr.io`
   - **Image and tag:** `niratiiyer/leftover-backend:latest`
   - **CPU and Memory:** 0.25 CPU cores, 0.5 Gi memory (the smallest)
   - **Environment variables**: click **+ Add** for each:

     | Name | Source | Value |
     |---|---|---|
     | `DATABASE_URL` | Manual entry | your Neon connection string |
     | `SECRET_KEY` | Manual entry | a new random string: run `python3 -c "import secrets; print(secrets.token_hex(32))"` |
     | `TIMEZONE` | Manual entry | `America/New_York` |

   - Click **Next: Bindings**, then **Next: Ingress**.

4. **Ingress** tab:
   - **Ingress:** Enabled
   - **Ingress traffic:** Accepting traffic from anywhere
   - **Ingress type:** HTTP
   - **Target port:** `8000`

5. Click **Review + create**, then **Create**. Wait 2–5 minutes until it says **Your deployment is complete**.

6. Click **Go to resource**. Copy the **Application Url** (like `https://leftover-api.purplesky-1234.eastus.azurecontainerapps.io`).

7. Check it works: open `<Application Url>/health` in your browser. It should show `{"status":"ok"}`.
   The first visit can take ~20 seconds while the app wakes up.

8. Tell the app its own address: in the left menu click **Containers** (or **Application → Containers**) → **Edit and deploy** →
   click the container → **Environment variables** → add `BASE_URL` = the Application Url → **Save** → **Create**.

## Part 5: Create the React dashboard (leftover-web)

Repeat Part 4 with these differences:

- **Container app name:** `leftover-web`
- **Container Apps environment:** pick the existing `leftover-env` (don't make a new one)
- **Image and tag:** `niratiiyer/leftover-frontend:latest`
- **Environment variables:** just one:

  | Name | Value |
  |---|---|
  | `BACKEND_URL` | the backend's Application Url from Part 4, step 6, **with no slash at the end** |

- **Target port:** `80`

When it's done, open its **Application Url**. You should see the dashboard with the chart and the
"Available now" table. Log in with an account you made on the main site to claim food.

## Part 6: Updating after you change the code

1. Push your change to `main` and wait for the CI run to go green (it publishes new images).
2. In the portal, open `leftover-api` (or `leftover-web`) → **Revisions and replicas** → **Create new revision** → **Create**.
   Azure downloads the newest image.

## Part 7: Observability (logs and a dashboard)

Every request the backend handles is logged as one line of JSON, for example:

```json
{"timestamp": "2026-10-21T15:26:09Z", "method": "GET", "endpoint": "/api/listings", "status": 200, "duration_ms": 26.58}
```

### Option A: Azure's built-in logs (free, nothing to sign up for)

1. Open `leftover-api` → **Monitoring** → **Logs**. Close any pop-up of sample queries.
2. Paste this query and click **Run**:

   ```kusto
   ContainerAppConsoleLogs_CL
   | where ContainerAppName_s == "leftover-api" and Log_s startswith "{"
   | extend e = parse_json(Log_s)
   | summarize requests = count() by bin(TimeGenerated, 5m), endpoint = tostring(e.endpoint)
   | render timechart
   ```

   If it says the table doesn't exist, use `ContainerAppConsoleLogs` instead, with the columns `ContainerAppName` and `Log`
   (newer environments use those names).
3. You get a chart of request counts per endpoint. Screenshot it for your README.

### Option B: Datadog

1. Sign up at https://www.datadoghq.com. Students can check the GitHub Student Developer Pack
   (https://education.github.com/pack) for a Datadog offer; otherwise use the free trial. Check what each includes.
2. Look at the address bar once you're logged in. The part after `app.` is your **site**,
   e.g. `app.datadoghq.com` → `datadoghq.com`, `us5.datadoghq.com` → `us5.datadoghq.com`.
3. Go to **Organization Settings → API Keys**, create a key, and copy it.
4. In Azure, open `leftover-api` → **Containers** → **Edit and deploy** → the container → **Environment variables**, add:

   | Name | Value |
   |---|---|
   | `DD_API_KEY` | the key |
   | `DD_SITE` | your site from step 2 |
   | `DD_ENV` | `prod` |

   Click **Save** → **Create**.
5. Use the site for a minute, then in Datadog open **Logs → Explorer** and search `service:leftover`. Your requests appear.
6. Make a dashboard: **Dashboards → New Dashboard** → add a **Timeseries** widget → data source **Logs**,
   query `service:leftover`, **count**, grouped by `@endpoint`. Screenshot it for your README.
