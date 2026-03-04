# CloudFuze Chatbot

AI-powered internal knowledge assistant for the CloudFuze team.

---

## External API

The chatbot exposes a simple REST endpoint so external users (friends, integrations, scripts) can ask questions **without needing a Microsoft login**.

### Endpoint

```
POST /api/external/chat
```

### Authentication

Pass your API key as a Bearer token in the `Authorization` header:

```
Authorization: Bearer <YOUR_API_KEY>
```

> Contact the CloudFuze dev team to get an API key.

### Request body

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | string | Yes | The question to ask (max 2000 chars) |
| `session_id` | string | No | Reuse a session ID to keep conversation context |

### Response

| Field | Type | Description |
|---|---|---|
| `answer` | string | The chatbots answer |
| `session_id` | string | Session ID (pass this back for follow-up questions) |
| `elapsed_ms` | int | Time taken to generate the answer (ms) |

---

### Examples

**cURL**

```bash
curl -X POST https://ai.cloudfuze.com/api/external/chat \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is CloudFuze Migrate?"}'
```

**Python**

```python
import requests

API_KEY = "<YOUR_API_KEY>"
BASE_URL = "https://ai.cloudfuze.com"

def ask(question: str, session_id: str = None):
    resp = requests.post(
        f"{BASE_URL}/api/external/chat",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"question": question, "session_id": session_id},
    )
    resp.raise_for_status()
    return resp.json()

# Single question
result = ask("What is CloudFuze Migrate?")
print(result["answer"])

# Multi-turn conversation
r1 = ask("What connectors does CloudFuze Migrate support?")
r2 = ask("What about Google Workspace?", session_id=r1["session_id"])
print(r2["answer"])
```

**JavaScript / Node.js**

```js
const API_KEY = "<YOUR_API_KEY>";
const BASE_URL = "https://ai.cloudfuze.com";

async function ask(question, sessionId = null) {
  const res = await fetch(`${BASE_URL}/api/external/chat`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  return res.json();
}

const { answer, session_id } = await ask("What is CloudFuze Manage?");
console.log(answer);
```

---

## Configuration (for admins)

Add the following to the servers `.env` file to enable the external API:

```env
# Comma-separated list of valid API keys
EXTERNAL_API_KEYS=key1,key2,key3
```

- If `EXTERNAL_API_KEYS` is not set, the endpoint returns `503 Service Unavailable`.
- Generate a secure key with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Each friend/integration should have their own key so you can revoke individually.

---

## Local development

```bash
# Backend
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8002 --reload

# Frontend
cd frontend
npm install
npm run dev
```

API documentation (Swagger UI) is available at `http://localhost:8002/docs`.
