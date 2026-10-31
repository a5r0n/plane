import pytest
from rest_framework.test import APIClient


@pytest.mark.unit
def test_ping():
    response = APIClient().get("/api/ext/ping/")
    assert response.status_code == 200
    assert response.json() == {"squadron": "ok"}
