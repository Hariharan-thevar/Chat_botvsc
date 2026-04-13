# MomoStrap Chatbot 🛍️
AI-powered customer support chatbot built with Flask + Claude (Anthropic).

---

## Files in this project

```
momostrap-chatbot/
├── app.py            ← Flask backend (API + DB + serves index.html)
├── index.html        ← Chat UI frontend
├── requirements.txt  ← Python dependencies
├── render.yaml       ← Render deployment config (auto-detected)
├── .gitignore
└── README.md
```

---

## Run locally (before deploying)

### Step 1 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 2 — Set your Anthropic API key
```bash
# macOS / Linux
export ANTHROPIC_API_KEY=sk-ant-your-key-here

# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"
```
Get a key at: https://console.anthropic.com/

### Step 3 — Start the server
```bash
python app.py
```

### Step 4 — Open in browser
Visit http://localhost:5000 — the chat UI loads directly.

---

## Deploy to Render (step by step)

### Step 1 — Push code to GitHub

```bash
# In your project folder
git init
git add .
git commit -m "MomoStrap chatbot initial commit"
```

Go to https://github.com/new and create a new repository (public or private).
Then push:

```bash
git remote add origin https://github.com/YOUR_USERNAME/momostrap-chatbot.git
git branch -M main
git push -u origin main
```

---

### Step 2 — Create a Render account
Sign up at https://render.com using your GitHub account (easiest option).

---

### Step 3 — Create a Web Service on Render

1. In your Render dashboard click **New +** → **Web Service**
2. Click **Connect account** → authorize GitHub → find your repo → click **Connect**
3. Fill in the settings:

| Field            | Value                              |
|------------------|------------------------------------|
| Name             | `momostrap-chatbot`                |
| Region           | Singapore (closest to India)       |
| Branch           | `main`                             |
| Runtime          | `Python 3`                         |
| Build Command    | `pip install -r requirements.txt`  |
| Start Command    | `gunicorn app:app`                 |
| Instance Type    | **Free**                           |

4. Scroll down to **Environment Variables** and add:

| Key                  | Value                   |
|----------------------|-------------------------|
| `ANTHROPIC_API_KEY`  | `sk-ant-your-key-here`  |

5. Click **Create Web Service**.

Render will build and deploy. In ~3 minutes your app is live at:
```
https://momostrap-chatbot.onrender.com
```

---

### Step 4 — (Optional but recommended) Add a PostgreSQL database

The free tier has an **ephemeral filesystem** — `chat_history.db` is wiped on redeploy.
Add a free PostgreSQL database to persist chat history across deploys:

1. In Render dashboard: **New +** → **PostgreSQL**
2. Name it `momostrap-db`, choose **Free** plan → **Create Database**
3. Copy the **Internal Database URL**
4. Go back to your Web Service → **Environment** tab → add:

| Key            | Value                                      |
|----------------|--------------------------------------------|
| `DATABASE_URL` | *(paste the Internal Database URL here)*   |

The app detects this automatically and switches from SQLite to PostgreSQL.

---

### Step 5 — Every future deploy is automatic
Push any change to GitHub and Render redeploys automatically:
```bash
git add .
git commit -m "Update system prompt"
git push
```

---

## API endpoints

| Method | Endpoint              | What it does                       |
|--------|-----------------------|------------------------------------|
| GET    | `/`                   | Serves the chat UI                 |
| GET    | `/health`             | Health check                       |
| POST   | `/chat`               | Send a message, get bot reply      |
| GET    | `/history/<id>`       | Chat history for a session         |
| GET    | `/sessions`           | List all sessions (admin)          |
| GET    | `/faqs`               | FAQ list                           |

---

## Troubleshooting

| Problem                        | Fix                                                             |
|--------------------------------|-----------------------------------------------------------------|
| Build fails                    | Make sure `gunicorn` is in `requirements.txt`                   |
| `Application failed to respond`| Start Command must be `gunicorn app:app`                        |
| `401` error in chat            | Check `ANTHROPIC_API_KEY` in Render → Environment tab           |
| Chat history lost on redeploy  | Add a PostgreSQL database and set `DATABASE_URL` env var        |
| Slow first response (~30s)     | Free tier sleeps after 15 min idle — upgrade to Starter ($7/mo) |
| CORS errors                    | `API_BASE=""` in `index.html` means frontend calls same server  |
