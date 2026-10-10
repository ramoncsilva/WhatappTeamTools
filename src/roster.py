"""Cadastro de times/pessoas/tarefas: validacao e plano de sincronizacao. Puro, sem I/O."""

import re
from zoneinfo import ZoneInfo

SLUG = re.compile(r"^[a-z0-9-]{1,40}$")
SINGULAR = {"people": "person", "tasks": "task"}
MAX_TAREFAS = 99
MAX_PESSOAS_GRUPO = 7  # grupo da Meta: 8 participantes, incluindo o numero da empresa


def validar(roster):
    """Devolve (times_normalizados, avisos). Lanca ValueError apontando o campo."""
    if not isinstance(roster, dict) or not isinstance(roster.get("teams"), list):
        raise ValueError("roster.teams: esperado uma lista")
    times, avisos, ids = [], [], set()
    for i, t in enumerate(roster["teams"]):
        loc = f"teams[{i}]"
        tid = _slug(t.get("id"), f"{loc}.id")
        if tid in ids:
            raise ValueError(f"{loc}.id: duplicado ({tid})")
        ids.add(tid)
        tz = t.get("timezone") or "America/Sao_Paulo"
        try:
            ZoneInfo(tz)
        except Exception:
            raise ValueError(f"{loc}.timezone: fuso invalido ({tz})")
        pessoas = _itens(t.get("people"), f"{loc}.people")
        tarefas = _itens(t.get("tasks"), f"{loc}.tasks")
        if len(tarefas) > MAX_TAREFAS:
            raise ValueError(f"{loc}.tasks: no maximo {MAX_TAREFAS} tarefas por time")
        if len(pessoas) > MAX_PESSOAS_GRUPO:
            avisos.append(f"{tid}: {len(pessoas)} pessoas; um grupo da Meta comporta no maximo 8 participantes")
        times.append({
            "id": tid,
            "name": _nome(t.get("name"), f"{loc}.name"),
            "whatsapp_group_id": str(t.get("whatsapp_group_id") or ""),
            "timezone": tz,
            "active": bool(t.get("active", True)),
            "people": pessoas,
            "tasks": tarefas,
        })
    return times, avisos


def _slug(v, loc):
    if not isinstance(v, str) or not SLUG.match(v):
        raise ValueError(f"{loc}: id invalido (use [a-z0-9-]{{1,40}})")
    return v


def _nome(v, loc):
    if not isinstance(v, str) or not v.strip() or len(v.strip()) > 60 or "\n" in v or "\r" in v:
        raise ValueError(f"{loc}: nome vazio, com mais de 60 caracteres ou com quebra de linha")
    return v.strip()


def _itens(lista, loc):
    if not isinstance(lista, list):
        raise ValueError(f"{loc}: esperado uma lista")
    out, ids = [], set()
    for i, it in enumerate(lista):
        iid = _slug(it.get("id") if isinstance(it, dict) else None, f"{loc}[{i}].id")
        if iid in ids:
            raise ValueError(f"{loc}[{i}].id: duplicado ({iid})")
        ids.add(iid)
        out.append({"id": iid, "name": _nome(it.get("name"), f"{loc}[{i}].name")})
    return out


def planejar(atual, time, agora):
    """atual: resultado de store.load_team (ou None); time: item normalizado de validar();
    agora: ISO-8601 UTC. Devolve (ops, resumo). Idempotente: estado igual => ops vazias."""
    meta = (atual or {}).get("meta") or {}
    pessoas_a = (atual or {}).get("people", {})
    tarefas_a = (atual or {}).get("tasks", {})
    pesos_a = (atual or {}).get("h", {})
    ops = []
    resumo = {"team": time["id"],
              "created": {"people": [], "tasks": []}, "reactivated": {"people": [], "tasks": []},
              "deactivated": {"people": [], "tasks": []},
              "updated": {"team": False, "people": [], "tasks": []}, "weights_created": 0}

    novo_meta = {k: time[k] for k in ("name", "whatsapp_group_id", "timezone", "active")}
    if any(meta.get(k) != v for k, v in novo_meta.items()):
        ops.append({"op": "team", "item": novo_meta})
        resumo["updated"]["team"] = atual is not None

    zerar = set()  # pessoas que reentraram: contadores voltam a 0
    for kind, desejados, existentes in (("people", time["people"], pessoas_a), ("tasks", time["tasks"], tarefas_a)):
        ids = set()
        for it in desejados:
            ids.add(it["id"])
            cur = existentes.get(it["id"])
            item = {"name": it["name"], "active": True}
            if cur is None:
                resumo["created"][kind].append(it["id"])
                item["joined_at"] = agora
            elif not cur.get("active", True):
                resumo["reactivated"][kind].append(it["id"])
                item["joined_at"] = agora
                if kind == "people":
                    zerar.add(it["id"])
            elif cur.get("name") != it["name"]:
                resumo["updated"][kind].append(it["id"])
                item["joined_at"] = cur.get("joined_at", agora)
            else:
                continue
            if kind == "tasks":
                item.pop("joined_at", None)
            ops.append({"op": SINGULAR[kind], "id": it["id"], "item": item})
        for eid, cur in existentes.items():
            if eid not in ids and cur.get("active", True):
                resumo["deactivated"][kind].append(eid)
                ops.append({"op": "deactivate", "kind": SINGULAR[kind], "id": eid, "left_at": agora})

    todas_p = set(pessoas_a) | {p["id"] for p in time["people"]}
    todas_t = set(tarefas_a) | {t["id"] for t in time["tasks"]}
    for t in sorted(todas_t):
        for p in sorted(todas_p):
            if p in zerar:
                ops.append({"op": "weight", "task": t, "person": p, "reset": True})
            elif (t, p) not in pesos_a:
                ops.append({"op": "weight", "task": t, "person": p, "reset": False})
    resumo["weights_created"] = sum(1 for o in ops if o["op"] == "weight")
    return ops, resumo
