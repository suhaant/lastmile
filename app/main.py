# ponytail: minimal stand-in for the team's endpoint file so the demo runs
# end-to-end. Replace/merge when the real one lands — routes match the agreed
# contract: POST /repairs/submit, POST /repairs/{id}/book,
# GET /rent/status/{id}, POST /rent/remind/{id}.
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services import mock_provider, rent_ledger

from app.routers import voice
app.include_router(voice.router)

app = FastAPI(title="AI Landlord Agent")

REPAIRS: dict[str, dict] = {}

EMERGENCY_WORDS = ("leak", "burst", "flood", "no heat", "sparks", "smoke",
                   "gas", "sewage", "no power", "locked out")
CATEGORY_WORDS = {"plumbing": ("leak", "pipe", "drain", "toilet", "sink", "water"),
                  "electrical": ("outlet", "power", "light", "sparks", "breaker")}


class RepairRequest(BaseModel):
    tenant_id: str
    description: str
    urgency: str | None = None  # auto-classified if omitted


class BookingRequest(BaseModel):
    slot_id: str


@app.post("/repairs/submit")
def submit_repair(req: RepairRequest):
    text = req.description.lower()
    urgency = req.urgency or (
        "emergency" if any(w in text for w in EMERGENCY_WORDS) else "routine")
    category = next((cat for cat, words in CATEGORY_WORDS.items()
                     if any(w in text for w in words)), "general")
    repair_id = f"r{len(REPAIRS) + 1}"
    slots = mock_provider.get_available_slots(urgency, category, repair_id)
    REPAIRS[repair_id] = {"id": repair_id, "tenant_id": req.tenant_id,
                          "description": req.description, "urgency": urgency,
                          "category": category, "status": "awaiting_booking",
                          "slots": slots}
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
    return {"id": repair_id, "status": "booked", "booked_slot": slot}


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
    return result


@app.get("/rent/tenants")  # convenience for the demo UI dropdown
def rent_tenants():
    return rent_ledger.list_tenants()


@app.get("/")
def demo_page():
    return FileResponse(Path(__file__).parent / "static" / "demo.html")
