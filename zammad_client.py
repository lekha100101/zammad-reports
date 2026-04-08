import requests
from typing import Any, Dict, List
from app.config import settings

class ZammadClient:
    def __init__(self) -> None:
        self.base_url = settings.zammad_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token token={settings.zammad_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _get(self, endpoint: str, params: Dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url, params=params, timeout=60)
        response.raise_for_status()
        return response.json()

    def get_tickets_page(self, page: int = 1, per_page: int = 100) -> List[Dict[str, Any]]:
        return self._get("/api/v1/tickets", {
            "page": page,
            "per_page": per_page,
        })

    def search_tickets(self, query: str, page: int = 1, per_page: int = 100, expand: bool = False):
        return self._get("/api/v1/tickets/search", {
            "query": query,
            "page": page,
            "per_page": per_page,
            "expand": str(expand).lower(),
        })

    def get_time_accountings(self, ticket_id: int):
        return self._get(f"/api/v1/tickets/{ticket_id}/time_accountings")
