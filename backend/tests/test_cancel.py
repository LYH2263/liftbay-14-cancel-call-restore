from app.models.models import Building, ElevatorCar


def _make_building(db, name="测试楼", floors=20):
    b = Building(name=name, floors=floors)
    db.add(b)
    db.flush()
    return b


def _make_car(db, building_id, label="T1", floor=1, direction="idle", load=0, capacity=10):
    car = ElevatorCar(
        building_id=building_id, label=label, floor=floor,
        direction=direction, load=load, capacity=capacity,
    )
    db.add(car)
    db.flush()
    return car


def _create_call(client, building_id, floor=5, direction="up", passengers=1):
    r = client.post(
        "/api/calls",
        json={"building_id": building_id, "floor": floor, "direction": direction, "passengers": passengers},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_cancel_waiting_drops_congestion(client, db):
    b = _make_building(db)
    db.commit()
    call = _create_call(client, b.id, floor=5, passengers=3)

    cong = client.get("/api/congestion").json()
    assert cong == [{"floor": 5, "passengers": 3}]

    r = client.post(f"/api/calls/{call['id']}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    # 取消后不再计入拥堵，也不再出现在待派列表
    assert client.get("/api/congestion").json() == []
    calls = client.get("/api/calls").json()
    cancelled = [c for c in calls if c["id"] == call["id"]]
    assert cancelled and cancelled[0]["status"] == "cancelled"
    assert not [c for c in calls if c["status"] == "waiting"]

    # 回放留有取消记录
    logs = client.get("/api/replay").json()
    assert any(l["call_id"] == call["id"] and "取消" in l["detail"] for l in logs)


def test_cancel_assigned_rolls_back_load_and_car_reusable(client, db):
    b = _make_building(db)
    car = _make_car(db, b.id, floor=1, load=0, capacity=10)
    db.commit()
    call = _create_call(client, b.id, floor=7, passengers=4)

    r = client.post("/api/dispatch", json={"call_id": call["id"]})
    assert r.status_code == 200, r.text
    cars = client.get("/api/cars").json()
    assert cars[0]["load"] == 4
    assert cars[0]["floor"] == 7
    assert cars[0]["direction"] == "up"

    r = client.post(f"/api/calls/{call['id']}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    # 载荷回退到 0 → 方向回到 idle，楼层保持派工后的层
    cars = client.get("/api/cars").json()
    assert cars[0]["load"] == 0
    assert cars[0]["direction"] == "idle"
    assert cars[0]["floor"] == 7

    # 回放记录取消与载荷回退
    logs = client.get("/api/replay").json()
    assert any(l["call_id"] == call["id"] and l["car_id"] == car.id and "回退" in l["detail"] for l in logs)

    # 该车可再接新单
    call2 = _create_call(client, b.id, floor=3, passengers=2, direction="down")
    r = client.post("/api/dispatch", json={"call_id": call2["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "assigned"
    assert r.json()["assigned_car_id"] == car.id
    cars = client.get("/api/cars").json()
    assert cars[0]["load"] == 2


def test_cancel_assigned_partial_load_keeps_direction(client, db):
    b = _make_building(db)
    _make_car(db, b.id, floor=2, load=3, capacity=10)
    db.commit()
    call = _create_call(client, b.id, floor=6, passengers=2)
    assert client.post("/api/dispatch", json={"call_id": call["id"]}).status_code == 200

    r = client.post(f"/api/calls/{call['id']}/cancel")
    assert r.status_code == 200, r.text
    cars = client.get("/api/cars").json()
    # 只回退该笔乘客，剩余载荷非零时方向保持
    assert cars[0]["load"] == 3
    assert cars[0]["direction"] == "up"


def test_cancel_rejected_fails(client, db):
    b = _make_building(db)
    _make_car(db, b.id, floor=1, load=1, capacity=1)
    db.commit()
    call = _create_call(client, b.id, floor=5, passengers=1)

    r = client.post("/api/dispatch", json={"call_id": call["id"]})
    assert r.status_code == 409
    calls = client.get("/api/calls").json()
    assert calls[0]["status"] == "rejected"

    r = client.post(f"/api/calls/{call['id']}/cancel")
    assert r.status_code == 400


def test_cancel_missing_call_404(client):
    r = client.post("/api/calls/9999/cancel")
    assert r.status_code == 404
