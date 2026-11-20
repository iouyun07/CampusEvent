def login(client, student_id: str) -> None:
    with client.session_transaction() as sess:
        sess["student_id"] = student_id


def create_activity(
    client,
    conn,
    title: str = "测试活动",
    capacity: int = 2,
    policy: str = "direct",
    start_at: str = "2099-01-01 10:00",
) -> int:
    response = client.post(
        "/admin/activities/new",
        data={
            "title": title,
            "category": "测试",
            "start_at": start_at,
            "location": "测试地点",
            "capacity": str(capacity),
            "policy_type": policy,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    row = conn.execute(
        "SELECT activity_id FROM activities WHERE title = ?", (title,)
    ).fetchone()
    assert row is not None
    return row["activity_id"]


def register(client, activity_id: int):
    return client.post(
        f"/activities/{activity_id}/register", follow_redirects=True
    )


def cancel(client, registration_id: int):
    return client.post(
        f"/registrations/{registration_id}/cancel", follow_redirects=True
    )


def status_of(conn, registration_id: int) -> str:
    return conn.execute(
        "SELECT status FROM registrations WHERE registration_id = ?",
        (registration_id,),
    ).fetchone()["status"]


def latest_registration(conn, activity_id: int, student_id: str):
    return conn.execute(
        "SELECT * FROM registrations WHERE activity_id = ? AND student_id = ?"
        " ORDER BY registration_id DESC",
        (activity_id, student_id),
    ).fetchone()
