# ponytail: stand-in for the team's endpoint file so the demo runs
# end-to-end. Routes match the agreed contract: POST /repairs/submit,
# POST /repairs/{id}/book, GET /rent/status/{id}, POST /rent/remind/{id}.
# The agent auto-books on submit; /repairs/{id}/book remains for rebooking.
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.services import mock_provider, rent_ledger

from app.routers import voice
app.include_router(voice.router)

app = FastAPI(title="AI Landlord Agent")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

REPAIRS: dict[str, dict] = {}
ACTIVITY: list[dict] = []  # agent action feed shown on the landlord page

EMERGENCY_WORDS = ("leak", "burst", "flood", "no heat", "sparks", "smoke",
                   "gas", "sewage", "no power", "locked out")
CATEGORY_WORDS = {"plumbing": ("leak", "pipe", "drain", "toilet", "sink", "water"),
                  "electrical": ("outlet", "power", "light", "sparks", "breaker")}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log(kind: str, text: str, **extra) -> None:
    ACTIVITY.append({"ts": now(), "kind": kind, "text": text, **extra})


class RepairRequest(BaseModel):
    tenant_id: str
    description: str
    urgency: str | None = None  # auto-classified if omitted


class BookingRequest(BaseModel):
    slot_id: str


def fmt(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%a %d %b, %H:%M")


@app.post("/repairs/submit")
def submit_repair(req: RepairRequest):
    tenant = rent_ledger.get_status(req.tenant_id)
    if not tenant:
        raise HTTPException(404, "unknown tenant")
    text = req.description.lower()
    urgency = req.urgency or (
        "emergency" if any(w in text for w in EMERGENCY_WORDS) else "routine")
    category = next((cat for cat, words in CATEGORY_WORDS.items()
                     if any(w in text for w in words)), "general")
    repair_id = f"r{len(REPAIRS) + 1}"
    slots = mock_provider.get_available_slots(urgency, category, repair_id)

    # ponytail: greedy pick, no scheduling optimizer. Emergency = soonest,
    # routine = best rated (cheapest tiebreak).
    if urgency == "emergency":
        slot, reason = slots[0], "the soonest emergency slot"
    else:
        slot = max(slots, key=lambda s: (s["rating"], -s["callout_fee"]))
        reason = "the highest-rated contractor for the job"

    when = fmt(slot["start"])
    timeline = [
        {"ts": now(), "text": f"Got it — I’ve logged your report: “{req.description}”"},
        {"ts": now(), "text": f"This looks like "
                              f"{'an' if urgency[0] in 'aeiou' else 'a'} "
                              f"{urgency} {category} issue. "
                              f"Checking contractor availability…"},
        {"ts": now(), "text": f"✅ Booked {slot['contractor']} ({slot['rating']}★) "
                              f"for {when} — I picked {reason}. "
                              f"They’ll need about {slot['window_hours']}h access."},
    ]
    REPAIRS[repair_id] = {"id": repair_id, "tenant_id": req.tenant_id,
                          "description": req.description, "urgency": urgency,
                          "category": category, "status": "booked",
                          "booked_slot": slot, "timeline": timeline,
                          "slots": slots}
    log("repair", f"🔧 {tenant['name']} (unit {tenant['unit']}) reported: "
                  f"“{req.description}”", repair_id=repair_id)
    log("triage", f"🧠 Triaged {repair_id} as {urgency} / {category} — "
                  f"{len(slots)} slots found across "
                  f"{len({s['contractor'] for s in slots})} contractors",
        repair_id=repair_id)
    log("booking", f"📅 Auto-booked {slot['contractor']} ({slot['rating']}★, "
                   f"${slot['callout_fee']} callout) for {when} — {reason}. "
                   f"Tenant notified.", repair_id=repair_id)
    return REPAIRS[repair_id]


@app.post("/repairs/{repair_id}/book")
def book_repair(repair_id: str, req: BookingRequest):
    repair = REPAIRS.get(repair_id)
    if not repair:
        raise HTTPException(404, "unknown repair id")
    slot = next((s for s in repair["slots"] if s["slot_id"] == req.slot_id), None)
    if not slot:
        raise HTTPException(400, "slot not available for this repair")
    repair.update(status="booked", booked_slot=slot)
    repair["timeline"].append(
        {"ts": now(), "text": f"🔁 Rebooked: {slot['contractor']} for {fmt(slot['start'])}"})
    log("booking", f"🔁 {repair_id} rebooked to {slot['contractor']} "
                   f"for {fmt(slot['start'])}", repair_id=repair_id)
    return {"id": repair_id, "status": "booked", "booked_slot": slot}


@app.get("/repairs/{repair_id}/calendar.ics")
def repair_ics(repair_id: str):
    repair = REPAIRS.get(repair_id)
    if not repair or not repair.get("booked_slot"):
        raise HTTPException(404, "no booking for this repair")
    slot = repair["booked_slot"]
    tenant = rent_ledger.get_status(repair["tenant_id"])
    start = datetime.fromisoformat(slot["start"])
    end = start + timedelta(hours=slot["window_hours"])
    stamp = "%Y%m%dT%H%M%S"
    ics = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//AI Landlord Agent//EN",
        "BEGIN:VEVENT",
        f"UID:{repair_id}@ai-landlord-agent",
        f"DTSTAMP:{datetime.now().strftime(stamp)}",
        f"DTSTART:{start.strftime(stamp)}",
        f"DTEND:{end.strftime(stamp)}",
        f"SUMMARY:Repair visit — {slot['contractor']}",
        f"LOCATION:Unit {tenant['unit']}",
        f"DESCRIPTION:{repair['description']} ({repair['urgency']} "
        f"{repair['category']}) — booked by AI Landlord Agent",
        "END:VEVENT", "END:VCALENDAR"])
    return Response(ics, media_type="text/calendar", headers={
        "Content-Disposition": f'attachment; filename="repair-{repair_id}.ics"'})


@app.get("/rent/status/{tenant_id}")
def rent_status(tenant_id: str):
    status = rent_ledger.get_status(tenant_id)
    if not status:
        raise HTTPException(404, "unknown tenant")
    return status


@app.post("/rent/remind/{tenant_id}")
def rent_remind(tenant_id: str):
    result = rent_ledger.send_reminder(tenant_id)
    if not result:
        raise HTTPException(404, "unknown tenant")
    log("rent", f"💬 Sent payment reminder to "
                f"{rent_ledger.get_status(tenant_id)['name']} via {result['channel']}: "
                f"“{result['message']}”", tenant_id=tenant_id)
    return result


@app.get("/rent/tenants")
def rent_tenants():
    return rent_ledger.list_tenants()


@app.get("/tenant/{tenant_id}/feed")
def tenant_feed(tenant_id: str):
    tenant = rent_ledger.get_status(tenant_id)
    if not tenant:
        raise HTTPException(404, "unknown tenant")
    repairs = [r for r in REPAIRS.values() if r["tenant_id"] == tenant_id]
    return {"tenant": tenant, "repairs": repairs}


@app.get("/landlord/overview")
def landlord_overview():
    return {"tenants": rent_ledger.list_tenants(),
            "repairs": [{k: v for k, v in r.items() if k != "slots"}
                        for r in REPAIRS.values()],
            "events": ACTIVITY}


@app.get("/")
def index_page():
    return FileResponse(STATIC / "index.html")


@app.get("/tenant")
def tenant_page():
    return FileResponse(STATIC / "tenant.html")


@app.get("/landlord")
def landlord_page():
    return FileResponse(STATIC / "landlord.html")
