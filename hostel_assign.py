#!/usr/bin/env python3
"""
Hostel / lodge room assignment tool.

Assigns a batch of customers to rooms in one optimized pass.

Hard constraints (a customer can never violate these):
  * gender          - room is male / female / mixed
  * capacity        - room never overfilled
  * budget          - room price must fit the customer's nightly budget
  * accessibility   - customers needing an accessible room only get one
  * shared language - guests sharing a room must speak the same language

Soft preferences (scored, higher is better):
  * floor preference, room-type preference, packing rooms tightly,
    language affinity with roommates, keeping groups together,
    leaving premium (accessible) rooms free for those who need them.

Usage:
  python hostel_assign.py init                      # write sample rooms.json / customers.json
  python hostel_assign.py assign --rooms rooms.json --customers customers.json
  python hostel_assign.py demo                      # run on built-in sample data
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from typing import Optional

MALE, FEMALE, MIXED = "male", "female", "mixed"

ROOM_TYPES = ("private", "shared", "family")


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class Room:
    id: str
    number: str
    floor: int
    capacity: int
    gender: str                 # male | female | mixed
    price_per_night: float
    room_type: str = "shared"   # private | shared | family
    accessible: bool = False


@dataclass
class Customer:
    id: str
    name: str
    gender: str                 # male | female
    language: str
    budget_per_night: float
    preferred_floor: Optional[int] = None
    needs_accessible: bool = False
    preferred_room_type: Optional[str] = None   # private | shared | family
    group: Optional[str] = None                 # members of a group are kept together


@dataclass
class Assignment:
    customer_id: str
    room_id: str
    score: float


# --------------------------------------------------------------------------
# Constraint and scoring logic
# --------------------------------------------------------------------------

def occupants(rooms_assign: dict, room_id: str, customers: dict) -> list:
    return [customers[cid] for cid in rooms_assign.get(room_id, [])]


def room_compatible(room: Room, cust: Customer, current: list) -> Optional[str]:
    """Return None if the customer may join the room, else a rejection reason."""
    if len(current) >= room.capacity:
        return "full"
    if room.gender != MIXED and cust.gender != room.gender:
        return f"gender ({room.gender} room)"
    if cust.needs_accessible and not room.accessible:
        return "needs accessible room"
    if room.price_per_night > cust.budget_per_night:
        return f"over budget ({room.price_per_night:.0f} > {cust.budget_per_night:.0f})"
    if current and any(o.language != cust.language for o in current):
        return "language mismatch with roommates"
    return None


def score_room(room: Room, cust: Customer, current: list, group_size: int) -> float:
    """Higher score = better fit. Only called on compatible rooms."""
    score = 0.0

    if current:
        score += 30.0                      # joining existing same-language roommates
    if cust.preferred_floor is not None and room.floor == cust.preferred_floor:
        score += 20.0
    if cust.preferred_room_type and room.room_type == cust.preferred_room_type:
        score += 15.0
    if len(current) + 1 == room.capacity:
        score += 25.0                      # fills the room completely
    elif len(current) + 1 < room.capacity:
        score -= 5.0 * (room.capacity - (len(current) + 1))  # prefer tighter fits

    if room.accessible and not cust.needs_accessible:
        score -= 40.0                  # save accessible rooms for those who need them

    score -= room.price_per_night / 100.0  # mild nudge toward cheaper rooms
    return score


# --------------------------------------------------------------------------
# Batch optimizer
# --------------------------------------------------------------------------

def _group_key(cust: Customer) -> str:
    return cust.group or f"__solo_{cust.id}"


def assign_customers(rooms: list, customers: list) -> tuple:
    """
    Greedy most-constrained-first assignment with a repair pass.

    Returns (assignments, unassigned) where unassigned is a list of
    (customer, reason) tuples.
    """
    rooms_by_id = {r.id: r for r in rooms}
    custs_by_id = {c.id: c for c in customers}
    rooms_assign: dict = {}          # room_id -> [customer_id, ...]

    # Group customers so group members are placed together.
    groups: dict = {}
    for c in customers:
        groups.setdefault(_group_key(c), []).append(c)

    # Most constrained first: bigger groups, accessibility needs, smaller budgets.
    def constraint_rank(gkey: str) -> tuple:
        members = groups[gkey]
        return (
            -len(members),
            not any(m.needs_accessible for m in members),
            min(m.budget_per_night for m in members),
        )

    ordered = sorted(groups, key=constraint_rank)
    assignments: list = []
    unassigned: list = []

    for gkey in ordered:
        members = groups[gkey]
        placed = False

        # Try to fit the whole group into one room first (real groups only;
        # solo customers go through the scored path so they can join others).
        if len(members) > 1:
            best_group = None
            for room in rooms:
                if rooms_assign.get(room.id):
                    continue
                if room.capacity < len(members):
                    continue
                if any(room_compatible(room, m, []) for m in members):
                    continue
                total = sum(score_room(room, m, [], len(members)) for m in members)
                if best_group is None or total > best_group[0]:
                    best_group = (total, room)
            if best_group:
                room = best_group[1]
                rooms_assign[room.id] = [m.id for m in members]
                for m in members:
                    assignments.append(Assignment(m.id, room.id, best_group[0] / len(members)))
                continue

        # Otherwise place members one by one into best-scoring rooms.
        failed = []
        for m in members:
            best = None
            for room in rooms:
                current = occupants(rooms_assign, room.id, custs_by_id)
                reason = room_compatible(room, m, current)
                if reason:
                    continue
                s = score_room(room, m, current, len(members))
                if best is None or s > best[0]:
                    best = (s, room)
            if best:
                rooms_assign.setdefault(best[1].id, []).append(m.id)
                assignments.append(Assignment(m.id, best[1].id, best[0]))
            else:
                failed.append(m)

        for m in failed:
            reasons = []
            for room in rooms:
                current = occupants(rooms_assign, room.id, custs_by_id)
                reason = room_compatible(room, m, current)
                if reason:
                    reasons.append(f"{room.number}: {reason}")
            unassigned.append((m, "; ".join(reasons[:4]) or "no rooms left"))

    assignments.sort(key=lambda a: (rooms_by_id[a.room_id].number, a.customer_id))
    return assignments, unassigned


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def report(assignments, unassigned, rooms, customers) -> str:
    rooms_by_id = {r.id: r for r in rooms}
    custs_by_id = {c.id: c for c in customers}
    lines = []
    lines.append(f"{'Room':<8}{'Floor':<7}{'Guests':<28}{'Price':>8}  Notes")
    lines.append("-" * 78)

    by_room: dict = {}
    for a in assignments:
        by_room.setdefault(a.room_id, []).append(custs_by_id[a.customer_id])

    revenue = 0.0
    for room in sorted(rooms, key=lambda r: (r.floor, r.number)):
        guests = by_room.get(room.id, [])
        revenue += room.price_per_night if guests else 0.0
        names = ", ".join(g.name for g in guests) or "-"
        notes = []
        if room.accessible:
            notes.append("accessible")
        if guests and len(guests) < room.capacity:
            notes.append(f"{room.capacity - len(guests)} bed(s) free")
        lines.append(
            f"{room.number:<8}{room.floor:<7}{names:<28}{room.price_per_night:>8.0f}  "
            f"{', '.join(notes)}"
        )

    lines.append("-" * 78)
    occupied = sum(1 for r in rooms if by_room.get(r.id))
    lines.append(f"Rooms occupied: {occupied}/{len(rooms)}   Revenue/night: {revenue:.0f}")

    if unassigned:
        lines.append("\nUNASSIGNED:")
        for cust, reason in unassigned:
            lines.append(f"  {cust.name} ({cust.id}) - {reason}")
    else:
        lines.append("\nAll customers assigned.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Sample data
# --------------------------------------------------------------------------

SAMPLE_ROOMS = [
    {"id": "r1", "number": "101", "floor": 1, "capacity": 4, "gender": "mixed",
     "price_per_night": 40, "room_type": "shared", "accessible": False},
    {"id": "r2", "number": "102", "floor": 1, "capacity": 4, "gender": "female",
     "price_per_night": 38, "room_type": "shared", "accessible": False},
    {"id": "r3", "number": "103", "floor": 1, "capacity": 2, "gender": "male",
     "price_per_night": 55, "room_type": "private", "accessible": False},
    {"id": "r4", "number": "201", "floor": 2, "capacity": 6, "gender": "mixed",
     "price_per_night": 30, "room_type": "shared", "accessible": False},
    {"id": "r5", "number": "202", "floor": 2, "capacity": 2, "gender": "mixed",
     "price_per_night": 90, "room_type": "family", "accessible": True},
    {"id": "r6", "number": "203", "floor": 2, "capacity": 4, "gender": "male",
     "price_per_night": 42, "room_type": "shared", "accessible": False},
    {"id": "r7", "number": "301", "floor": 3, "capacity": 4, "gender": "female",
     "price_per_night": 45, "room_type": "shared", "accessible": False},
    {"id": "r8", "number": "302", "floor": 3, "capacity": 2, "gender": "mixed",
     "price_per_night": 70, "room_type": "private", "accessible": True},
]

SAMPLE_CUSTOMERS = [
    {"id": "c1", "name": "Alice", "gender": "female", "language": "en",
     "budget_per_night": 50, "preferred_floor": 2, "needs_accessible": False,
     "preferred_room_type": "shared", "group": None},
    {"id": "c2", "name": "Berta", "gender": "female", "language": "en",
     "budget_per_night": 45, "preferred_floor": None, "needs_accessible": False,
     "preferred_room_type": "shared", "group": None},
    {"id": "c3", "name": "Chen", "gender": "male", "language": "zh",
     "budget_per_night": 60, "preferred_floor": 1, "needs_accessible": False,
     "preferred_room_type": None, "group": None},
    {"id": "c4", "name": "Diego", "gender": "male", "language": "es",
     "budget_per_night": 35, "preferred_floor": None, "needs_accessible": False,
     "preferred_room_type": "shared", "group": "fam1"},
    {"id": "c5", "name": "Elena", "gender": "female", "language": "es",
     "budget_per_night": 35, "preferred_floor": None, "needs_accessible": False,
     "preferred_room_type": "family", "group": "fam1"},
    {"id": "c6", "name": "Frank", "gender": "male", "language": "en",
     "budget_per_night": 100, "preferred_floor": None, "needs_accessible": True,
     "preferred_room_type": None, "group": None},
    {"id": "c7", "name": "Grace", "gender": "female", "language": "fr",
     "budget_per_night": 40, "preferred_floor": 3, "needs_accessible": False,
     "preferred_room_type": "shared", "group": None},
    {"id": "c8", "name": "Hugo", "gender": "male", "language": "en",
     "budget_per_night": 30, "preferred_floor": None, "needs_accessible": False,
     "preferred_room_type": "shared", "group": None},
    {"id": "c9", "name": "Ivan", "gender": "male", "language": "ru",
     "budget_per_night": 25, "preferred_floor": None, "needs_accessible": False,
     "preferred_room_type": None, "group": None},
]


def load_rooms(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return [Room(**r) for r in json.load(f)]


def load_customers(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return [Customer(**c) for c in json.load(f)]


def write_samples() -> None:
    with open("rooms.json", "w", encoding="utf-8") as f:
        json.dump(SAMPLE_ROOMS, f, indent=2)
    with open("customers.json", "w", encoding="utf-8") as f:
        json.dump(SAMPLE_CUSTOMERS, f, indent=2)
    print("Wrote rooms.json and customers.json - edit them, then run:")
    print("  python hostel_assign.py assign --rooms rooms.json --customers customers.json")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Hostel room assignment")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="write sample rooms.json / customers.json to edit")

    a = sub.add_parser("assign", help="assign customers from JSON files")
    a.add_argument("--rooms", required=True)
    a.add_argument("--customers", required=True)
    a.add_argument("--json", action="store_true", help="emit assignments as JSON")

    sub.add_parser("demo", help="run on built-in sample data")

    args = parser.parse_args(argv)

    if args.command == "init":
        write_samples()
        return 0

    if args.command == "demo":
        rooms = [Room(**r) for r in SAMPLE_ROOMS]
        customers = [Customer(**c) for c in SAMPLE_CUSTOMERS]
    else:
        rooms = load_rooms(args.rooms)
        customers = load_customers(args.customers)

    assignments, unassigned = assign_customers(rooms, customers)

    if getattr(args, "json", False):
        out = {
            "assignments": [asdict(x) for x in assignments],
            "unassigned": [{"customer_id": c.id, "reason": r} for c, r in unassigned],
        }
        print(json.dumps(out, indent=2))
    else:
        print(report(assignments, unassigned, rooms, customers))

    return 1 if unassigned else 0


if __name__ == "__main__":
    sys.exit(main())
