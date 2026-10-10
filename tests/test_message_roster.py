import pytest

import message
import roster

A = [
    {"task": "ata", "task_name": "Ata da daily", "person": "bruno", "person_name": "Bruno", "p": 12 / 19},
    {"task": "cafe", "task_name": "Café", "person": "carla", "person_name": "Carla", "p": 0.75},
    {"task": "limpeza", "task_name": "Limpeza da sala", "person": "ana", "person_name": "Ana", "p": 2 / 3},
]


def test_render_sem_excecoes():
    texto = message.renderizar("Plataforma", "2026-W42", A, [])[0]
    assert "Semana 42/2026 (12/10 a 18/10)" in texto
    assert "*Ata da daily* → *Bruno* (63,2%)" in texto
    assert "*Café* → *Carla* (75,0%)" in texto
    assert "*Limpeza da sala* → *Ana* (66,7%)" in texto
    assert "Justificativas" not in texto


def test_justificativas_j1_j2_j4():
    a = [dict(A[0]), dict(A[1], person="bruno", person_name="Bruno")]
    j = message.justificar(a, "relaxed", 1, 2, {"ata": "bruno"}, ["Eva"])
    codigos = [x["code"] for x in j]
    assert codigos == ["J1", "J2", "J4"]
    texto = message.renderizar("T", "2026-W42", a, j)[0]
    assert "⚠️ *Justificativas*" in texto and "🆕 Eva entrou" in texto
    assert 'Bruno repete "Ata da daily"' in texto


def test_sanitiza_nomes_e_divide_mensagem_longa():
    assert message.limpar("*Ana_\n~Silva`") == "Ana Silva"
    muitas = [dict(A[0], task_name="T" * 80 + str(i)) for i in range(80)]
    partes = message.renderizar("Time", "2026-W42", muitas, [])
    assert len(partes) > 1 and all(len(p) <= 4096 for p in partes)


def test_compacto_uma_linha_e_limitado():
    muitas = [dict(A[0], task_name="Tarefa longa numero " + str(i)) for i in range(100)]
    time, sem, texto = message.compacto("Plataforma", "2026-W42", muitas, [])
    assert sem == "semana 42/2026" and "\n" not in texto and len(texto) <= 900


ROSTER = {"teams": [{"id": "plataforma", "name": "Plataforma", "whatsapp_group_id": "g",
                     "people": [{"id": "ana", "name": "Ana"}, {"id": "bruno", "name": "Bruno"}],
                     "tasks": [{"id": "ata", "name": "Ata"}]}]}


def test_validar_erros_apontam_o_campo():
    ok, _ = roster.validar(ROSTER)
    assert ok[0]["timezone"] == "America/Sao_Paulo"
    ruim = {"teams": [dict(ROSTER["teams"][0], people=[{"id": "Ana!", "name": "x"}])]}
    with pytest.raises(ValueError, match=r"teams\[0\]\.people\[0\]\.id"):
        roster.validar(ruim)
    with pytest.raises(ValueError, match="timezone"):
        roster.validar({"teams": [dict(ROSTER["teams"][0], timezone="Marte/Olimpo")]})


def _estado(ops):
    d = {"meta": None, "people": {}, "tasks": {}, "h": {}}
    for o in ops:
        if o["op"] == "team":
            d["meta"] = o["item"]
        elif o["op"] in ("person", "task"):
            d["people" if o["op"] == "person" else "tasks"][o["id"]] = o["item"]
        elif o["op"] == "deactivate":
            d["people" if o["kind"] == "person" else "tasks"][o["id"]]["active"] = False
        elif o["op"] == "weight":
            if o["reset"] or (o["task"], o["person"]) not in d["h"]:
                d["h"][(o["task"], o["person"])] = 0
    return d


def test_sync_cria_pesos_zero_e_e_idempotente():  # AC-05, AC-10
    t = roster.validar(ROSTER)[0][0]
    ops, r = roster.planejar(None, t, "2026-10-12T00:00:00Z")
    assert r["created"]["people"] == ["ana", "bruno"] and r["weights_created"] == 2
    d = _estado(ops)
    assert roster.planejar(d, t, "2026-10-13T00:00:00Z")[0] == []

    # entra Eva e sai Bruno
    t2 = dict(t, people=[{"id": "ana", "name": "Ana"}, {"id": "eva", "name": "Eva"}])
    d["h"][("ata", "bruno")] = 5
    ops2, r2 = roster.planejar(d, t2, "2026-10-14T00:00:00Z")
    assert r2["created"]["people"] == ["eva"] and r2["deactivated"]["people"] == ["bruno"]
    assert {(o["task"], o["person"]) for o in ops2 if o["op"] == "weight"} == {("ata", "eva")}

    # Bruno volta: contadores zerados (reentrada)
    d2 = _estado(ops + ops2)
    d2["h"][("ata", "bruno")] = 5
    ops3, r3 = roster.planejar(d2, t, "2026-10-20T00:00:00Z")
    assert r3["reactivated"]["people"] == ["bruno"]
    assert any(o["op"] == "weight" and o["person"] == "bruno" and o["reset"] for o in ops3)
