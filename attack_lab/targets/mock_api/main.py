from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import time

app = FastAPI(title="Mock Upstream API (deliberately vulnerable for the AEGIS attack lab)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

USERS = {
    1: {"id": 1, "name": "Alice Anderson", "email": "alice@example.com", "ssn": "123-45-6789", "api_key": "sk-alice-secret-1234"},
    2: {"id": 2, "name": "Bob Baker", "email": "bob@example.com", "ssn": "987-65-4321", "api_key": "sk-bob-secret-5678"},
    3: {"id": 3, "name": "Mallory Mason", "email": "mallory@example.com", "ssn": "111-22-3333", "api_key": "sk-mallory-secret-9012"},
    4: {"id": 4, "name": "Carol Chen", "email": "carol@example.com", "ssn": "444-55-6666", "api_key": "sk-carol-secret-3456"},
}

ORDERS = {
    101: {"id": 101, "user_id": 1, "total": 250.00, "card": "4111 1111 1111 1111"},
    102: {"id": 102, "user_id": 2, "total": 89.50, "card": "5555 5555 5555 4444"},
    103: {"id": 103, "user_id": 3, "total": 1200.00, "card": "3782 822463 10005"},
}

CUSTOMERS = [
    {"id": 1, "name": "Acme Corp", "billing_email": "billing@acme.com"},
    {"id": 2, "name": "Globex", "billing_email": "finance@globex.com"},
]


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/public/products")
async def public_products():
    return {"products": [{"id": 1, "name": "Widget"}]}


@app.get("/api/public/products")
async def api_public_products():
    return {"products": [{"id": 1, "name": "Widget"}]}


@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    user = USERS.get(user_id)
    if user is None:
        return JSONResponse(status_code=404, content={"detail": "user not found"})
    return user


@app.get("/api/users")
async def list_users():
    return list(USERS.values())


@app.get("/api/orders/{order_id}")
async def get_order(order_id: int):
    order = ORDERS.get(order_id)
    if order is None:
        return JSONResponse(status_code=404, content={"detail": "order not found"})
    return order


@app.get("/api/customers")
async def list_customers():
    return CUSTOMERS


@app.get("/api/payments/summary")
async def payments_summary():
    return {"payments": [{"id": 1, "amount": 250.0}]}


@app.get("/admin/users")
async def admin_users():
    return {"users": list(USERS.values()), "system": "admin panel"}


@app.get("/admin/metrics")
async def admin_metrics():
    return {"metrics": {"active_users": 4, "db": "postgres"}}


class ChatRequest(BaseModel):
    messages: list[dict] | None = None
    prompt: str | None = None


@app.post("/ai/chat")
async def ai_chat(body: ChatRequest, request: Request):
    prompt = ""
    if body.prompt:
        prompt = body.prompt
    elif body.messages:
        prompt = " ".join(m.get("content", "") for m in body.messages if isinstance(m, dict))
    if "internal" in prompt.lower() or "secret" in prompt.lower() or "api.key" in prompt.lower():
        return {"response": "Here is the internal data: db_host=10.0.4.12, api_key=sk-mock-internal-key-999, admin_email=admin@corp.internal"}
    return {"response": f"Echo: {prompt[:80]}", "model": "mock-llm"}


@app.post("/llm/completions")
async def llm_completions(body: ChatRequest):
    prompt = body.prompt or ""
    return {"choices": [{"message": {"content": f"Mock completion: {prompt[:60]}"}}]}


class ToolExec(BaseModel):
    tool: str
    arguments: dict = {}


@app.post("/api/tools/execute")
async def execute_tool(body: ToolExec):
    tool = body.tool
    args = body.arguments or {}
    if tool == "get_user":
        uid = args.get("user_id")
        user = USERS.get(int(uid)) if uid else None
        return {"result": user or {"error": "not found"}}
    if tool == "get_order":
        oid = args.get("order_id")
        order = ORDERS.get(int(oid)) if oid else None
        return {"result": order or {"error": "not found"}}
    if tool == "search_database":
        query = str(args.get("query", ""))[:100]
        return {"result": {"rows": [{"table": "customers", "query": query}]}}
    if tool == "create_ticket":
        return {"result": {"ticket_id": 9001, "status": "created"}}
    if tool == "send_email":
        return {"result": {"sent": True, "to": args.get("to")}}
    if tool == "upload_file":
        return {"result": {"uploaded": True, "name": args.get("filename")}}
    if tool == "delete_user":
        uid = args.get("user_id")
        return {"result": {"deleted": True, "user_id": uid}}
    if tool == "execute_payment":
        return {"result": {"payment_id": 7001, "amount": args.get("amount")}}
    if tool == "grant_admin":
        return {"result": {"granted": True, "user_id": args.get("user_id")}}
    return {"result": {"error": "unknown tool"}}


@app.get("/status")
async def status():
    return {"status": "up", "uptime_sec": int(time.time() % 100000)}


@app.get("/search")
async def search(q: str = ""):
    return {"query": q}
