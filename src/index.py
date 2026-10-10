"""Ponto de entrada da Lambda: despacha por `action`. Ver specs/001-sorteio-semanal/contracts/events.md."""

import json
import logging
import secrets
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config
import message
import roster
import store
import whatsapp
from draw import sortear

log = logging.getLogger()
log.setLevel(logging.INFO)


def _log(**campos):  # sem nomes de pessoas e sem token (NFR-05)
    log.info(json.dumps(campos, ensure_ascii=False))


def _agora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _semana(tz):
    iso = datetime.now(ZoneInfo(tz)).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ---------------------------------------------------------------- weekly / resend
def _enviar(tid, semana, sorteio, time_nome, grupo):
    partes = message.renderizar(time_nome, semana, sorteio["assignments"], sorteio["justifications"])
    params = message.compacto(time_nome, semana, sorteio["assignments"], sorteio["justifications"])
    envio = whatsapp.Envio(config.access_token())
    anteriores = int(sorteio.get("send_attempts", 0))
    try:
        mid = whatsapp.enviar(envio, grupo, partes, params, config.env("WA_SEND_MODE", "auto"))
    except whatsapp.MetaError as e:
        store.atualizar_sorteio(tid, semana, send_attempts=anteriores + envio.tentativas,
                                last_error=f"{e.kind}:{e.status}:{e.code}")
        return {"status": "PENDING", "error": f"{e.kind}:{e.status}:{e.code}"}
    store.atualizar_sorteio(tid, semana, status="SENT", sent_at=_agora(), wa_message_id=mid,
                            send_attempts=anteriores + envio.tentativas, last_error="")
    return {"status": "SENT"}


def _sortear_time(meta, semana, dry_run):
    tid = meta["id"]
    d = store.carregar_time(tid)
    pessoas = [i for i, p in sorted(d["people"].items()) if p.get("active", True)]
    tarefas = [i for i, t in sorted(d["tasks"].items()) if t.get("active", True)]
    if not pessoas:
        return {"status": "SKIPPED", "reason": "no_people"}
    if not tarefas:
        return {"status": "SKIPPED", "reason": "no_tasks"}
    if not meta.get("whatsapp_group_id") and not dry_run:
        raise ValueError("no_group_id")

    ant = store.sorteio_anterior(tid, semana)
    prev = {a["task"]: a["person"] for a in ant["assignments"]} if ant else {}
    h = {(p, t): c for (t, p), c in d["h"].items()}
    res = sortear(pessoas, tarefas, h, prev, secrets.randbits(63),
                  int(config.env("DRAW_MAX_ATTEMPTS", "200")))
    for a in res["assignments"]:
        a["task_name"] = d["tasks"][a["task"]]["name"]
        a["person_name"] = d["people"][a["person"]]["name"]
    novos = [d["people"][p]["name"] for p in pessoas
             if ant and d["people"][p].get("joined_at", "") > ant.get("created_at", "")]
    res["justifications"] = message.justificar(res["assignments"], res["mode"], res["n"], res["m"], prev, novos)
    res.update(status="PENDING", created_at=_agora(), send_attempts=0, week=semana)
    if dry_run:
        return {"status": "DRY_RUN", "mode": res["mode"], "attempts": res["attempts"], "assignments": res["assignments"],
                "message": message.renderizar(meta["name"], semana, res["assignments"], res["justifications"])}
    if not store.gravar_sorteio(tid, semana, res):
        return None  # perdeu a corrida: o chamador relê o sorteio vencedor
    return dict(res, _novo=True)


def _weekly_time(meta, semana_arg, dry_run):
    tid = meta["id"]
    semana = semana_arg or _semana(meta.get("timezone") or "America/Sao_Paulo")
    existente = store.obter_sorteio(tid, semana)
    if existente and dry_run:  # dry_run nunca envia nem regrava
        return {"team": tid, "week": semana, "status": "SKIPPED", "reason": f"already_drawn_{existente['status'].lower()}"}
    novo = None
    if not existente:
        novo = _sortear_time(meta, semana, dry_run)
        if novo is None:
            existente = store.obter_sorteio(tid, semana)
        elif novo["status"] in ("SKIPPED", "DRY_RUN"):
            return dict(novo, team=tid, week=semana)
        else:
            existente = novo
    if existente.get("status") == "SENT":
        return {"team": tid, "week": semana, "status": "SKIPPED", "reason": "already_sent"}
    r = _enviar(tid, semana, existente, meta["name"], meta["whatsapp_group_id"])
    return dict(r, team=tid, week=semana, mode=existente["mode"], attempts=existente["attempts"],
                assignments=len(existente["assignments"]))


def _selecionar(team):
    times = [t for t in store.listar_times() if t.get("active", True)]
    if team:
        times = [t for t in times if t["id"] == team]
        if not times:
            raise ValueError(f"time inexistente ou inativo: {team}")
    return times


def _por_time(times, fn):
    resultados, falhou = [], False
    for meta in times:
        try:
            r = fn(meta)
        except Exception as e:  # isolamento por time (FR-24)
            r = {"team": meta["id"], "status": "ERROR", "error": str(e)[:300]}
        if r["status"] in ("ERROR", "PENDING"):
            falhou = True
        _log(**{k: v for k, v in r.items() if k not in ("assignments", "message")})
        resultados.append(r)
    return resultados, falhou


# ---------------------------------------------------------------- acoes
def _weekly(ev):
    dry = bool(ev.get("dry_run"))
    rs, falhou = _por_time(_selecionar(ev.get("team")), lambda m: _weekly_time(m, ev.get("week"), dry))
    return {"ok": not falhou, "teams": rs}, falhou and not dry


def _resend(ev):
    tid, semana = ev.get("team"), ev.get("week")
    if not tid or not semana:
        raise ValueError("resend exige team e week")
    meta = _selecionar(tid)[0]
    sorteio = store.obter_sorteio(tid, semana)
    if not sorteio:
        raise ValueError(f"nao ha sorteio para {tid} em {semana}")
    r = _enviar(tid, semana, sorteio, meta["name"], meta["whatsapp_group_id"])
    return {"ok": r["status"] == "SENT", "teams": [dict(r, team=tid, week=semana)]}, r["status"] != "SENT"


def _revert(ev):
    tid = ev.get("team")
    if not tid:
        raise ValueError("revert exige team")
    ultimo = store.ultimo_sorteio(tid)
    if not ultimo:
        raise ValueError(f"time {tid} nao tem sorteio para reverter")
    store.reverter_sorteio(tid, ultimo)
    return {"ok": True, "reverted": ultimo["sk"].split("#", 1)[1], "decremented": len(ultimo["assignments"])}, False


def _sync_roster(ev):
    times, avisos = roster.validar(ev.get("roster"))
    dry, agora, resumos = bool(ev.get("dry_run")), _agora(), []
    for t in times:
        d = store.carregar_time(t["id"])
        ops, resumo = roster.planejar(d if d["meta"] else None, t, agora)
        if not dry:
            store.aplicar_ops(t["id"], ops)
        resumos.append(resumo)
    return {"ok": True, "dry_run": dry, "warnings": avisos, "teams": resumos}, False


ACOES = {"weekly": _weekly, "resend": _resend, "revert": _revert, "sync_roster": _sync_roster}


def handler(event, context=None):
    ev = event or {}
    acao = ev.get("action", "weekly")
    if acao not in ACOES:
        raise ValueError(f"action desconhecida: {acao}")
    t0 = time.monotonic()
    resposta, falhar = ACOES[acao](ev)
    _log(action=acao, ok=resposta.get("ok"), duration_ms=int((time.monotonic() - t0) * 1000))
    if falhar:  # depois de processar todos os times: dispara retry e alerta
        raise RuntimeError(f"{acao} falhou: " + json.dumps(resposta, ensure_ascii=False, default=str)[:1500])
    return resposta
