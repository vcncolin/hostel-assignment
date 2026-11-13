# Hostel Room Assignment

Assigns hostel/lodge guests to rooms in one optimized batch pass.

**Hard rules** (never violated): gender (male/female/mixed rooms), capacity,
nightly budget, accessibility needs, and a shared-language rule — guests in a
shared room must speak the same language.

**Preferences** (optimized automatically): floor preference, room-type
preference, packing rooms tightly, shared-language roommates, keeping groups
together, and reserving accessible rooms for guests who need them.

## Run the web UI

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000, edit the room and guest lists (JSON), and click
**Assign rooms**.

## Run the CLI

```bash
python hostel_assign.py demo                      # built-in sample data
python hostel_assign.py init                      # write editable rooms.json / customers.json
python hostel_assign.py assign --rooms rooms.json --customers customers.json
python hostel_assign.py assign --rooms rooms.json --customers customers.json --json
```

The CLI exits with code 1 when any guest could not be assigned.

## Data format

Rooms: `id`, `number`, `floor`, `capacity`, `gender` (`male`/`female`/`mixed`),
`price_per_night`, `room_type` (`private`/`shared`/`family`), `accessible`.

Customers: `id`, `name`, `gender`, `language`, `budget_per_night`,
`preferred_floor`, `needs_accessible`, `preferred_room_type`, `group`
(guests sharing a `group` value are placed together when possible).

Guests who cannot be placed are reported with the exact reason per room.
