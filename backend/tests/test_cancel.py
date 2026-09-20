from app.models.models import Building, CallTicket, ElevatorCar


def _make_building_car(db_factory, *, load=0, capacity=10, floor=1, direction="idle"):
    db = db_factory()
    b = Building(name="测试楼", floors=18)
    db.add(b)
    db.flush()
    car = ElevatorCar(
        building_id=b.id,
        label="T1",
        floor=floor,
        direction=direction,
        load=load,
        capacity=capacity,
    )
    db.add(car)
    db.commit()
    ids = (b.id, car.id)
    db.close()
    return ids


def _new_call(client, building_id, floor, direction="up", passengers=1):
    r = client.post(
        "/api/calls",
        json={
            "building_id": building_id,
            "floor": floor,
            "direction": direction,
            "passengers": passengers,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _get_car(db_factory, car_id):
    db = db_factory()
    car = db.get(ElevatorCar, car_id)
    snapshot = (car.floor, car.direction, car.load, car.capacity)
    db.close()
    return snapshot


def test_cancel_waiting_lowers_congestion(client, db_factory):
    bid, _ = _make_building_car(db_factory)
    _new_call(client, bid, floor=5, passengers=2)
    c2 = _new_call(client, bid, floor=5, passengers=1)

    r = client.get("/api/congestion")
    assert r.status_code == 200
    assert r.json() == [{"floor": 5, "passengers": 3}]

    r = client.post(f"/api/calls/{c2['id']}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    # 拥堵人数下降；已取消呼梯不再计入
    r = client.get("/api/congestion")
    assert r.json() == [{"floor": 5, "passengers": 2}]

    # 不再出现在待派列表：派工接口拒绝已取消呼梯
    r = client.post("/api/dispatch", json={"call_id": c2["id"]})
    assert r.status_code == 400

    # 回放记下取消
    r = client.get("/api/replay")
    assert any(c2["id"] == log["call_id"] and "取消" in log["detail"] for log in r.json())


def test_cancel_assigned_reverts_load_and_car_accepts_again(client, db_factory):
    # 派工前轿厢空闲在 1F；派工后被搬到呼梯层
    bid, car_id = _make_building_car(db_factory, load=0, floor=1, direction="idle")
    c = _new_call(client, bid, floor=9, direction="up", passengers=3)

    r = client.post("/api/dispatch", json={"call_id": c["id"]})
    assert r.status_code == 200, r.text
    assert _get_car(db_factory, car_id) == (9, "up", 3, 10)

    r = client.post(f"/api/calls/{c['id']}/cancel")
    assert r.status_code == 200, r.text

    # 载荷回退为零 → 方向 idle，楼层保持派工后的 9F
    assert _get_car(db_factory, car_id) == (9, "idle", 0, 10)

    # 该车可再接新单
    c2 = _new_call(client, bid, floor=12, direction="up", passengers=2)
    r = client.post("/api/dispatch", json={"call_id": c2["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "assigned"
    assert body["assigned_car_id"] == car_id
    assert _get_car(db_factory, car_id) == (12, "up", 2, 10)


def test_cancel_assigned_keeps_direction_while_others_remain(client, db_factory):
    # 轿厢原本已有 2 名乘客，取消后载荷非零，方向与楼层维持派工后状态
    bid, car_id = _make_building_car(
        db_factory, load=2, floor=3, direction="up"
    )
    c = _new_call(client, bid, floor=9, direction="up", passengers=3)
    client.post("/api/dispatch", json={"call_id": c["id"]})
    assert _get_car(db_factory, car_id) == (9, "up", 5, 10)

    r = client.post(f"/api/calls/{c['id']}/cancel")
    assert r.status_code == 200, r.text
    assert _get_car(db_factory, car_id) == (9, "up", 2, 10)


def test_cancel_rejected_fails(client, db_factory):
    # 唯一轿厢满员 → 派工被拒
    bid, car_id = _make_building_car(db_factory, load=8, capacity=8, floor=5)
    c = _new_call(client, bid, floor=5, passengers=1)

    r = client.post("/api/dispatch", json={"call_id": c["id"]})
    assert r.status_code == 409

    r = client.post(f"/api/calls/{c['id']}/cancel")
    assert r.status_code == 400

    db = db_factory()
    ticket = db.get(CallTicket, c["id"])
    assert ticket.status == "rejected"
    car = db.get(ElevatorCar, car_id)
    assert car.load == 8  # 载荷未受影响
    db.close()
