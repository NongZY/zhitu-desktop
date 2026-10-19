def test_registered_user_can_log_in_and_read_profile(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "learner@example.com",
            "password": "Learning123!",
            "name": "测试学习者",
        },
    )
    assert register.status_code == 201
    assert register.json()["email"] == "learner@example.com"
    assert "role" not in register.json()
    assert "hashed_password" not in register.json()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "Learning123!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["name"] == "测试学习者"
    assert "role" not in profile.json()


def test_registration_does_not_accept_a_role(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "role-injection@example.com",
            "password": "Learning123!",
            "name": "学习者",
            "role": "privileged",
        },
    )
    assert response.status_code == 422
