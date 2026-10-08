import httpx
from bot.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

def get_supabase_headers(is_storage=False):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    if not is_storage:
        headers["Content-Type"] = "application/json"

    return headers

# STATE MANGEMENT
async def get_user_state(user_id: int):
    url = f"{SUPABASE_URL}/rest/v1/user_state?user_id=eq.{user_id}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_supabase_headers())
        if response.status_code == 200 and response.json():
            return response.json()[0]
    return {"user_id": user_id, "state": "idle", "data": {}}

async def set_user_state(user_id: int, state: str, data: dict = None):
    if data is None:
        data = {}

    url = f"{SUPABASE_URL}/rest/v1/user_state"
    payload = {
        "user_id": user_id,
        "state": state,
        "data": data,
        "updated_at": "now()"
    }

    headers = get_supabase_headers()
    headers["Prefer"] = "resolution=merge-duplicates"

    async with httpx.AsyncClient() as client:
        await client.post(url, headers=headers, json=payload)

# STORAGE UPLOAD
async def upload_proof(file_bytes: bytes, file_name: str) -> str:
    url = f"{SUPABASE_URL}/storage/v1/object/bukti/{file_name}"
    headers = get_supabase_headers(is_storage=True)
    headers["Content-Type"] = "image/jpeg"

    async with httpx.AsyncClient() as client:
        res = await client.post(url, headers=headers, content=file_bytes)

        # Public URL structure:
        # https://<project>.supabase.co/storage/v1/object/public/bukti/<file_name>
        if res.status_code in [200, 201]:
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/bukti/{file_name}"
            return public_url

    return ""
