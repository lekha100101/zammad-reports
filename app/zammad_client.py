from __future__ import annotations

from typing import Any
import requests
from app.config import settings


class ZammadClient:
    def __init__(self) -> None:
        if not settings.zammad_url:
            raise ValueError("ZAMMAD_URL is empty")
        if not settings.zammad_token:
            raise ValueError("ZAMMAD_TOKEN is empty")

        self.base_url = settings.zammad_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token token={settings.zammad_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "zammad-reports-mvp/1.0",
            }
        )
        self.verify_ssl = settings.zammad_verify_ssl

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url, params=params, timeout=120, verify=self.verify_ssl)
        response.raise_for_status()
        return response.json()

    def list_paginated(self, endpoint: str, per_page: int | None = None):
        page = 1
        per_page = per_page or settings.zammad_per_page
        while True:
            items = self._get(endpoint, {"page": page, "per_page": per_page})
            if not items:
                break
            if not isinstance(items, list):
                raise ValueError(f"Unexpected response for {endpoint}: expected list")
            yield from items
            if len(items) < per_page:
                break
            page += 1

    def list_tickets(self):
        yield from self.list_paginated("/api/v1/tickets")

    def list_users(self):
        yield from self.list_paginated("/api/v1/users")

    def list_groups(self):
        yield from self.list_paginated("/api/v1/groups")

    def list_organizations(self):
        yield from self.list_paginated("/api/v1/organizations")

    def get_time_accountings(self, ticket_id: int):
        return self._get(f"/api/v1/tickets/{ticket_id}/time_accountings")

    def healthcheck(self):
        items = self._get("/api/v1/users", {"page": 1, "per_page": 1})
        return {"ok": isinstance(items, list)}
