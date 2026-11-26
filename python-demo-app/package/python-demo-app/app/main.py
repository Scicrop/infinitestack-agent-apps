import asyncio

from fastapi import Depends, FastAPI, WebSocket
from fastapi.responses import HTMLResponse, StreamingResponse
from infinitestack_app import Identity, IdentityError, identity_from_headers, is_user

app = FastAPI(title="Python Demo App")

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Python Demo App</title>
<style>body{font-family:system-ui,sans-serif;margin:24px;color:#1f2937}code{background:#f3f4f6;padding:2px 6px;border-radius:4px}
section{margin:16px 0;padding:12px 16px;border:1px solid #e5e7eb;border-radius:8px}</style></head><body>
<h1>Python Demo App</h1>
<section><h2>Who am I</h2><pre id="me">...</pre></section>
<section><h2>Server-sent events</h2><pre id="sse"></pre></section>
<section><h2>WebSocket echo</h2><input id="msg" value="hello"> <button id="send">Send</button><pre id="ws"></pre></section>
<script>
const base = location.pathname.replace(/\\/$/, "");
fetch(base + "/me").then(r => r.json()).then(j => me.textContent = JSON.stringify(j, null, 2));
const es = new EventSource(base + "/events");
es.onmessage = e => { sse.textContent += e.data + "\\n"; };
const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + base + "/ws");
ws.onmessage = e => { document.getElementById("ws").textContent += e.data + "\\n"; };
send.onclick = () => ws.send(msg.value);
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.get("/status", response_class=HTMLResponse)
def status():
    return "<p>Python Demo App is running.</p>"


@app.get("/me")
def me(user: Identity = Depends(is_user)):
    return {"user_id": user.user_id, "username": user.username, "role": user.role, "principal_type": user.principal_type}


@app.get("/events")
async def events():
    async def stream():
        for i in range(1, 6):
            yield f"data: tick {i}\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@app.websocket("/ws")
async def echo(websocket: WebSocket):
    try:
        name = identity_from_headers(websocket.headers).username
    except IdentityError:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            text = await websocket.receive_text()
            await websocket.send_text(f"{name}: {text}")
    except Exception:
        pass
