"""Fluxo completo com DynamoDB simulado (moto) e servidor HTTP local no lugar da Meta."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import boto3
import pytest
from moto import mock_aws

import config
import store
import whatsapp

ROSTER = {"teams": [{"id": "plataforma", "name": "Plataforma", "whatsapp_group_id": "grp1",
                     "people": [{"id": "ana", "name": "Ana"}, {"id": "bruno", "name": "Bruno"}],
                     "tasks": [{"id": "ata", "name": "Ata"}, {"id": "cafe", "name": "Café"},
                               {"id": "limpeza", "name": "Limpeza"}]}]}


class FakeMeta:
    """Servidor local que imita o Graph API; `resposta` controla o que devolve."""

    def __init__(self):
        self.chamadas, self.respostas = [], []
        meta = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                meta.chamadas.append((corpo, self.headers["Authorization"]))
                status, resp = meta.respostas.pop(0) if meta.respostas else (200, {"messages": [{"id": "wamid.1"}]})
                self.send_response(status)
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode())

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}"


@pytest.fixture
def ambiente(monkeypatch):
    with mock_aws():
        db = boto3.client("dynamodb")
        db.create_table(TableName="t", BillingMode="PAY_PER_REQUEST",
                        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                                              {"AttributeName": "sk", "AttributeType": "S"}],
                        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}])
        meta = FakeMeta()
        for k, v in {"TABLE_NAME": "t", "WA_BASE_URL": meta.url, "WA_API_VERSION": "v25.0", "WA_PHONE_NUMBER_ID": "123",
                     "WA_SEND_MODE": "auto", "WA_TEMPLATE_NAME": "sorteio_semanal", "ACCESS_TOKEN_PARAM": "/x"}.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setattr(config, "_token", "TOKEN-DE-TESTE")
        monkeypatch.setattr(store, "_tabela", None)
        monkeypatch.setattr(whatsapp.time, "sleep", lambda s: None)
        import index
        index.handler({"action": "sync_roster", "roster": ROSTER})
        yield index, meta
        meta.srv.shutdown()


def cnt(tid="plataforma"):
    return store.carregar_time(tid)["h"]


def test_sync_idempotente_e_pesos_zero(ambiente):  # AC-05, AC-10
    index, _ = ambiente
    assert cnt() == {(t, p): 0 for t in ("ata", "cafe", "limpeza") for p in ("ana", "bruno")}
    r = index.handler({"action": "sync_roster", "roster": ROSTER})
    assert r["teams"][0]["weights_created"] == 0 and r["teams"][0]["created"]["people"] == []


def test_dry_run_nao_grava_nem_envia(ambiente):  # AC-11
    index, meta = ambiente
    r = index.handler({"action": "weekly", "dry_run": True})
    assert r["teams"][0]["status"] == "DRY_RUN" and "Sorteio semanal" in r["teams"][0]["message"][0]
    assert meta.chamadas == [] and store.ultimo_sorteio("plataforma") is None


def test_sorteio_envio_idempotencia_e_cargas(ambiente):  # AC-03, AC-08
    index, meta = ambiente
    r = index.handler({"action": "weekly"})
    assert r["teams"][0]["status"] == "SENT" and len(meta.chamadas) == 1
    corpo, auth = meta.chamadas[0]
    assert corpo["recipient_type"] == "group" and corpo["to"] == "grp1" and auth == "Bearer TOKEN-DE-TESTE"
    assert "Justificativas" in corpo["text"]["body"]                       # 3 tarefas, 2 pessoas => J1
    assert sorted(cnt().values()) == [0, 0, 0, 1, 1, 1]
    antes = dict(cnt())
    r2 = index.handler({"action": "weekly"})
    assert r2["teams"][0]["reason"] == "already_sent" and len(meta.chamadas) == 1 and cnt() == antes


def test_falha_no_whatsapp_deixa_pending_e_resend_nao_mexe_nos_contadores(ambiente):  # AC-09
    index, meta = ambiente
    meta.respostas = [(401, {"error": {"code": 190, "message": "token expirado"}})]
    with pytest.raises(RuntimeError):
        index.handler({"action": "weekly"})
    d = store.ultimo_sorteio("plataforma")
    assert d["status"] == "PENDING" and d["last_error"].startswith("auth")
    antes = dict(cnt())
    semana = d["sk"].split("#", 1)[1]
    assert index.handler({"action": "resend", "team": "plataforma", "week": semana})["ok"]
    assert store.obter_sorteio("plataforma", semana)["status"] == "SENT" and cnt() == antes


def test_modo_auto_cai_para_template_quando_janela_fechada(ambiente):
    index, meta = ambiente
    meta.respostas = [(400, {"error": {"code": 131047, "message": "janela fechada"}})]
    assert index.handler({"action": "weekly"})["ok"]
    assert [c[0]["type"] for c in meta.chamadas] == ["text", "template"]
    params = meta.chamadas[1][0]["template"]["components"][0]["parameters"]
    assert len(params) == 3 and "\n" not in params[2]["text"]


def test_revert_e_p1_na_semana_seguinte(ambiente):
    index, meta = ambiente
    index.handler({"action": "weekly", "week": "2026-W41"})
    primeiro = store.obter_sorteio("plataforma", "2026-W41")
    index.handler({"action": "weekly", "week": "2026-W42"})
    seg = store.obter_sorteio("plataforma", "2026-W42")
    # 2 pessoas, 3 tarefas: P1 respeitavel => ninguem repete a mesma tarefa
    prev = {a["task"]: a["person"] for a in primeiro["assignments"]}
    assert seg["mode"] == "strict" and all(prev[a["task"]] != a["person"] for a in seg["assignments"])
    assert sum(cnt().values()) == 6
    r = index.handler({"action": "revert", "team": "plataforma"})
    assert r["reverted"] == "2026-W42" and sum(cnt().values()) == 3
    assert store.obter_sorteio("plataforma", "2026-W42") is None


def test_corrida_grava_so_um_sorteio(ambiente):  # FR-17
    index, _ = ambiente
    index.handler({"action": "weekly", "week": "2026-W43"})
    d = store.obter_sorteio("plataforma", "2026-W43")
    assert store.gravar_sorteio("plataforma", "2026-W43", dict(d)) is False
    assert sum(cnt().values()) == 3


def test_sem_group_id_e_erro(ambiente):
    index, _ = ambiente
    r2 = json.loads(json.dumps(ROSTER))
    r2["teams"][0]["whatsapp_group_id"] = ""
    index.handler({"action": "sync_roster", "roster": r2})
    with pytest.raises(RuntimeError, match="no_group_id"):
        index.handler({"action": "weekly"})
    assert store.ultimo_sorteio("plataforma") is None


def test_token_nunca_aparece_na_resposta_nem_nos_logs(ambiente, caplog):  # AC-12
    index, _ = ambiente
    caplog.set_level("INFO")
    r = index.handler({"action": "weekly"})
    assert "TOKEN-DE-TESTE" not in json.dumps(r) and "TOKEN-DE-TESTE" not in caplog.text
