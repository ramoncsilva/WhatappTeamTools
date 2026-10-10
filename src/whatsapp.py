"""Envio ao WhatsApp (Meta Cloud API) com urllib. Ver contracts/whatsapp.md."""

import json
import time
import urllib.error
import urllib.request

from config import env

JANELA_FECHADA = {131047}  # [validar T-00] codigo observado em conversas 1:1
RETENTAVEL = {130429, 131056}
ESPERAS = (1, 2, 4)


class MetaError(Exception):
    def __init__(self, status, code, message, kind):
        super().__init__(f"HTTP {status} code={code} kind={kind}: {message}")
        self.status, self.code, self.kind = status, code, kind


def _classificar(status, code):
    if status == 401 or code == 190:
        return "auth"
    if code in JANELA_FECHADA:
        return "window"
    if status == 429 or status >= 500 or code in RETENTAVEL:
        return "retry"
    return "fatal"


def _post(url, payload, token, timeout=10):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8")).get("error", {})
        except Exception:
            err = {}
        code = err.get("code")
        raise MetaError(e.code, code, str(err.get("message", e.reason))[:300], _classificar(e.code, code)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise MetaError(0, None, f"rede: {e}", "retry") from None


class Envio:
    """Executa chamadas com backoff e conta quantas foram feitas (send_attempts)."""

    def __init__(self, token, post=_post, dormir=time.sleep):
        base = env("WA_BASE_URL", "https://graph.facebook.com")
        self.url = f"{base}/{env('WA_API_VERSION', 'v25.0')}/{env('WA_PHONE_NUMBER_ID')}/messages"
        self.token, self.post, self.dormir = token, post, dormir
        self.tentativas = 0

    def _chamar(self, payload):
        for espera in (0,) + ESPERAS:
            if espera:
                self.dormir(espera)
            self.tentativas += 1
            try:
                resp = self.post(self.url, payload, self.token)
                return resp["messages"][0]["id"]
            except MetaError as e:
                if e.kind != "retry":
                    raise
                ultimo = e
        raise ultimo

    def _base(self, grupo):
        return {"messaging_product": "whatsapp", "recipient_type": "group", "to": grupo}

    def texto(self, grupo, partes):
        ids = [self._chamar(dict(self._base(grupo), type="text", text={"preview_url": False, "body": p}))
               for p in partes]
        return ids[-1]

    def template(self, grupo, params):
        payload = dict(self._base(grupo), type="template", template={
            "name": env("WA_TEMPLATE_NAME"), "language": {"code": env("WA_TEMPLATE_LANG", "pt_BR")},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]})
        return self._chamar(payload)


def enviar(envio, grupo, partes, params, modo):
    """modo: text | template | auto. Devolve o id da ultima mensagem."""
    if modo == "template":
        return envio.template(grupo, params)
    try:
        return envio.texto(grupo, partes)
    except MetaError as e:
        if modo == "auto" and e.kind == "window" and env("WA_TEMPLATE_NAME"):
            return envio.template(grupo, params)
        raise
