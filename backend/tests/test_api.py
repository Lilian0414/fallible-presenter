FORBIDDEN = {"errors", "contains_error", "error_ids", "identified_error_id", "original_statement", "modified_statement", "correct_answer", "total_errors"}


def assert_public(value):
    if isinstance(value, dict):
        assert not (set(value) & FORBIDDEN)
        for item in value.values(): assert_public(item)
    elif isinstance(value, list):
        for item in value: assert_public(item)


def create(client, source):
    response = client.post("/api/sessions", json={"source_text": source})
    assert response.status_code == 200
    assert_public(response.json())
    return response.json()


def test_end_to_end_and_advancement(client, source):
    created = create(client, source)
    sid, first = created["session_id"], created["first_segment"]
    current = client.get(f"/api/sessions/{sid}/current")
    assert current.json()["index"] == 0
    assert current.json()["segment"] == first
    assert_public(current.json())
    assert client.get(f"/api/sessions/{sid}/result").status_code == 409
    response = client.post(f"/api/sessions/{sid}/continue")
    assert response.json()["index"] == 1
    assert_public(response.json())
    assert client.post(f"/api/sessions/{sid}/challenge", json={"segment_id": first["id"], "reason": "This is stale"}).status_code == 409
    while not response.json().get("completed"):
        response = client.post(f"/api/sessions/{sid}/continue")
    result = client.get(f"/api/sessions/{sid}/result")
    assert result.status_code == 200
    assert result.json()["summary"]["missed"] == result.json()["summary"]["total_errors"]


def test_known_correct_and_corrupt_challenges(client, source):
    created = create(client, source); sid = created["session_id"]
    correct = client.post(f"/api/sessions/{sid}/challenge", json={"segment_id": "segment_001", "reason": "I doubt this supported point"})
    assert correct.status_code == 200 and correct.json()["valid"] is False
    assert_public(correct.json())
    client.post(f"/api/sessions/{sid}/continue")
    corrupt = client.post(f"/api/sessions/{sid}/challenge", json={"segment_id": "segment_002", "reason": "The source actually says exercise improves health, so the direction was reversed"})
    assert corrupt.status_code == 200 and corrupt.json()["valid"] is True
    assert corrupt.json()["reasoning_score"] >= 4
    assert_public(corrupt.json())
    assert client.post(f"/api/sessions/{sid}/challenge", json={"segment_id": "segment_002", "reason": "again"}).status_code == 409
