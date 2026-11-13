import json

import app as web

c = web.app.test_client()

# 1. Home page renders with sample data prefilled
r = c.get("/")
assert r.status_code == 200, r.status_code
html = r.get_data(as_text=True)
assert "textarea" in html and "Assign rooms" in html
print("GET / ->", r.status_code, "| sample data prefilled OK")

# 2. Valid assignment round-trip
rooms = json.dumps(web.SAMPLE_ROOMS)
customers = json.dumps(web.SAMPLE_CUSTOMERS)
r = c.post("/assign", data={"rooms": rooms, "customers": customers})
html = r.get_data(as_text=True)
assert r.status_code == 200, r.status_code
assert "Rooms occupied: 5/8" in html, "assignment result missing"
assert "UNASSIGNED" in html
print("POST /assign valid ->", r.status_code, "| result rendered OK")

# 3. All-assignable dataset -> everyone placed
rooms2 = [{"id": "r1", "number": "101", "floor": 1, "capacity": 4, "gender": "mixed",
           "price_per_night": 20, "room_type": "shared", "accessible": False}]
custs2 = [{"id": "c1", "name": "A", "gender": "male", "language": "en", "budget_per_night": 25},
          {"id": "c2", "name": "B", "gender": "male", "language": "en", "budget_per_night": 25}]
r = c.post("/assign", data={"rooms": json.dumps(rooms2), "customers": json.dumps(custs2)})
html = r.get_data(as_text=True)
assert r.status_code == 200 and "All customers assigned." in html
print("POST /assign everyone-placed -> OK")

# 4. Invalid JSON -> 400 with error message
r = c.post("/assign", data={"rooms": "{bad json", "customers": "[]"})
html = r.get_data(as_text=True)
assert r.status_code == 400 and "invalid JSON" in html
print("POST /assign invalid JSON -> 400 with error shown OK")

# 5. Wrong fields in an item -> 400
r = c.post("/assign", data={"rooms": json.dumps([{"nope": 1}]), "customers": customers})
assert r.status_code == 400 and "wrong fields" in r.get_data(as_text=True)
print("POST /assign wrong fields -> 400 with error shown OK")

print()
print("ALL WEB TESTS PASSED")
