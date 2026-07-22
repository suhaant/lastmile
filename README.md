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

## Known risks
- ActionLayer's call tool behavior/latency unknown until hands-on session
  — calendar + vision logic is independent, build/demo those first if
  voice proves flaky.
- If live voice is unreliable during the demo, fall back to text-transcript
  simulation so core logic still demos cleanly.

## Vision demo photos
- **LOW:** loose cabinet knob; door still works.
- **MEDIUM:** cabinet door detached from one hinge, with no sharp debris.
- **MEDIUM:** dripping faucet with all water contained in a bowl.
- **HIGH:** steady under-sink leak visibly spreading across the cabinet floor.
- **EMERGENCY:** use a safe, disconnected damaged-cable prop and describe an
  outlet that sparked with a burning smell. Never stage a real electrical hazard.

Use clear JPEGs under 1 MB and pre-run the exact demo photos against the selected
Novita model before presenting.
