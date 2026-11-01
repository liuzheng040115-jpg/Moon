"""在服务器上跑：登录 NapCat WebUI -> 用 QQ 号+密码登录 QQ。"""

import hashlib
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:6099"
WEBUI_TOKEN = "297a8d1981da"
QQ = "3680764546"
PASSWORD = "qhs644602"


def post(path, body, jwt=None):
    headers = {"Content-Type": "application/json"}
    if jwt:
        headers["Authorization"] = "Bearer " + jwt
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:  # noqa: BLE001
        return -1, repr(e)


h = hashlib.sha256((WEBUI_TOKEN + ".napcat").encode()).hexdigest()
status, body = post("/api/auth/login", {"hash": h, "totpCode": ""})
print("auth:", status, body[:300])

try:
    data = json.loads(body).get("data")
except Exception:  # noqa: BLE001
    data = None

jwt = None
if isinstance(data, str):
    jwt = data
elif isinstance(data, dict):
    jwt = (
        data.get("Credential")
        or data.get("credential")
        or data.get("token")
        or data.get("jwt")
        or data.get("accessToken")
    )

print("jwt:", (jwt or "")[:48])

if jwt:
    md5 = hashlib.md5(PASSWORD.encode()).hexdigest()
    status, body = post("/api/QQLogin/PasswordLogin", {"uin": QQ, "passwordMd5": md5}, jwt)
    print("login:", status, body[:800])
