"""Small web UI for the hostel room assignment tool."""

import json

from flask import Flask, render_template, request

from hostel_assign import (
    SAMPLE_CUSTOMERS,
    SAMPLE_ROOMS,
    Customer,
    Room,
    assign_customers,
    report,
)

app = Flask(__name__)


def parse_items(raw: str, cls, label: str):
    """Parse a JSON list into dataclass instances, raising ValueError on bad input."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: invalid JSON - {exc}")
    if not isinstance(data, list):
        raise ValueError(f"{label}: expected a JSON list")
    items = []
    for i, item in enumerate(data, 1):
        try:
            items.append(cls(**item))
        except TypeError as exc:
            raise ValueError(f"{label}: item {i} has wrong fields - {exc}")
    return items


@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        rooms_json=json.dumps(SAMPLE_ROOMS, indent=2),
        customers_json=json.dumps(SAMPLE_CUSTOMERS, indent=2),
        result=None,
        error=None,
    )


@app.route("/assign", methods=["POST"])
def assign():
    rooms_json = request.form.get("rooms", "")
    customers_json = request.form.get("customers", "")
    try:
        rooms = parse_items(rooms_json, Room, "Rooms")
        customers = parse_items(customers_json, Customer, "Customers")
        if not rooms:
            raise ValueError("Rooms: list is empty")
        if not customers:
            raise ValueError("Customers: list is empty")
    except ValueError as exc:
        return render_template(
            "index.html",
            rooms_json=rooms_json,
            customers_json=customers_json,
            result=None,
            error=str(exc),
        ), 400

    assignments, unassigned = assign_customers(rooms, customers)
    result = report(assignments, unassigned, rooms, customers)
    return render_template(
        "index.html",
        rooms_json=rooms_json,
        customers_json=customers_json,
        result=result,
        error=None,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
