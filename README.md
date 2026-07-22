# AI Landlord Agent (Hackathon Skeleton)

Scope: repair scheduling (photo intake -> severity -> book slot -> voice confirm)
+ mocked rent collection status + voice-call layer tying it together.

Explicitly out of scope: eviction management, legal advice, tax auditing —
cut for liability reasons, see PRD notes.

## Stack
- FastAPI backend
- Novita: vision model (severity scoring), reasoning model (slot matching)
- ActionLayer: voice calls (repair confirmation, rent reminders)
- Google Calendar API: real slot booking

## Build order (do this first, in order)
1. **Google Calendar auth** (`app/services/calendar_service.py`) — do this
   immediately, it's the dependency everything else needs. OAuth setup
   can eat unexpected time.
2. **Mock provider** (`app/services/mock_provider.py`) — already stubbed
   with fake slot data, adjust as needed.
3. **Novita vision call** (`app/services/vision.py`) — wire the real API
   call in place of the keyword-based stub.
4. **ActionLayer voice call** (`app/services/voice_service.py`) — wire in
   once calendar + vision work standalone.
5. End-to-end test, then polish demo narration.

## Run locally
```bash
pip install -r requirements.txt
cp .env.example .env  # fill in keys
uvicorn app.main:app --reload
```

## Endpoints
- `POST /repairs/submit` — tenant submits photo + description
- `POST /repairs/{ticket_id}/book` — triggers scheduling + voice confirm
- `GET /rent/status/{tenant_id}` — mocked rent ledger status
- `POST /rent/remind/{tenant_id}` — triggers voice reminder
- `POST /voice/call` — direct call trigger (mostly used internally)
- `POST /voice/webhook` — ActionLayer callback receiver

## Demo — presenter script (~2 minutes, two windows)

The demo UI is served by the app itself at **http://localhost:8000** —
no separate frontend to run. Everything is mocked in-memory
(`app/services/`); restart the server to reset state.

Setup: open **/tenant** and **/landlord** in two windows side by side.
The landlord feed polls every 2s, so it updates live while you drive
the tenant window.

1. **Emergency repair** — tenant window, pick **Rosa Delgado**, click the
   **💧 Burst pipe** preset → Send. Agent replies in-chat: triaged
   *emergency / plumbing*, auto-booked the **soonest** emergency-capable
   contractor (same evening). Click **📅 Add to calendar** → downloads a
   real .ics.
2. **Landlord window** — the report → triage → booking trail has already
   appeared in the live feed; sidebar shows the repair with an
   *emergency* pill.
3. **Routine contrast** — tenant window, switch to **Dev Patel**, click
   **🔌 Dead outlet** → Send. This time the agent picks the
   **highest-rated** electrician days out, business hours.
4. **Rent** — landlord sidebar: Marcus Webb is 2 months overdue. Click
   **Remind** → mocked SMS appears in the feed, button flips to *Sent ✓*.

## Known risks
- ActionLayer's call tool behavior/latency unknown until hands-on session
  — calendar + vision logic is independent, build/demo those first if
  voice proves flaky.
- If live voice is unreliable during the demo, fall back to text-transcript
  simulation so core logic still demos cleanly.
