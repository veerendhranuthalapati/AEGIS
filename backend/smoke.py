"""Quick smoke test hitting the real app + DB via ASGI transport."""
import asyncio

import httpx


async def main() -> None:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Admin@1234"},
        )
        print("login:", r.status_code)
        print(r.text[:800])
        if r.status_code == 200:
            token = r.json()["access_token"]
            r2 = await client.get(
                "/api/analytics/overview",
                headers={"Authorization": f"Bearer {token}"},
            )
            print("overview:", r2.status_code, r2.text[:800])


asyncio.run(main())
