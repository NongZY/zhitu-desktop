def test_registered_user_can_log_in_and_read_profile(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "student@example.com",
            "password": "Learning123!",
            "name": "测试学生",
            "role": "student",
        },
    )
    assert register.status_code == 201
    assert register.json()["email"] == "student@example.com"
    assert "hashed_password" not in register.json()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "Learning123!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["name"] == "测试学生"
    assert profile.json()["role"] == "student"
