"""Todo o acesso ao DynamoDB (tabela unica). Ver specs/001-sorteio-semanal/data-model.md."""

from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from config import env

_tabela = None
V = 1


def tabela():
    global _tabela
    if _tabela is None:
        _tabela = boto3.resource("dynamodb").Table(env("TABLE_NAME"))
    return _tabela


def _dec(o):
    if isinstance(o, float):
        return Decimal(str(o))
    if isinstance(o, dict):
        return {k: _dec(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_dec(v) for v in o]
    return o


def _undec(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    if isinstance(o, dict):
        return {k: _undec(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_undec(v) for v in o]
    return o


def _query(**kw):
    itens = []
    while True:
        r = tabela().query(**kw)
        itens += r["Items"]
        if "LastEvaluatedKey" not in r:
            return [_undec(i) for i in itens]
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def listar_times():
    """AP-1: [{id, name, whatsapp_group_id, timezone, active}]"""
    return [dict(i, id=i["sk"].split("#", 1)[1]) for i in _query(KeyConditionExpression=Key("pk").eq("TEAMS"))]


def carregar_time(tid):
    """AP-2: {id, meta|None, people{id:item}, tasks{id:item}, h{(tarefa,pessoa):cnt}}"""
    r = tabela().get_item(Key={"pk": "TEAMS", "sk": f"TEAM#{tid}"}).get("Item")
    itens = _query(KeyConditionExpression=Key("pk").eq(f"TEAM#{tid}") & Key("sk").between("PERSON#", "WEIGHT#~"))
    out = {"id": tid, "meta": _undec(r) if r else None, "people": {}, "tasks": {}, "h": {}}
    for i in itens:
        tipo, _, resto = i["sk"].partition("#")
        if tipo == "PERSON":
            out["people"][resto] = i
        elif tipo == "TASK":
            out["tasks"][resto] = i
        elif tipo == "WEIGHT":
            t, p = resto.split("#")
            out["h"][(t, p)] = int(i.get("cnt", 0))
    return out


def obter_sorteio(tid, semana):
    """AP-4"""
    r = tabela().get_item(Key={"pk": f"TEAM#{tid}", "sk": f"DRAW#{semana}"}).get("Item")
    return _undec(r) if r else None


def sorteio_anterior(tid, semana):
    """AP-3: ultimo sorteio estritamente anterior a `semana`."""
    itens = _query(KeyConditionExpression=Key("pk").eq(f"TEAM#{tid}") & Key("sk").between("DRAW#", f"DRAW#{semana}"),
                   ScanIndexForward=False, Limit=2)
    for i in itens:
        if i["sk"] != f"DRAW#{semana}":
            return i
    return None


def ultimo_sorteio(tid):
    itens = _query(KeyConditionExpression=Key("pk").eq(f"TEAM#{tid}") & Key("sk").begins_with("DRAW#"),
                   ScanIndexForward=False, Limit=1)
    return itens[0] if itens else None


def _cancelada_por_condicao(exc):
    razoes = exc.response.get("CancellationReasons") or []
    return any(r.get("Code") == "ConditionalCheckFailed" for r in razoes)


def gravar_sorteio(tid, semana, registro):
    """Transacao: DRAW (so se nao existir) + ADD cnt 1 em cada WEIGHT. False se perdeu a corrida."""
    nome = tabela().name
    item = dict(registro, pk=f"TEAM#{tid}", sk=f"DRAW#{semana}", v=V)
    acoes = [{"Put": {"TableName": nome, "Item": _dec(item), "ConditionExpression": "attribute_not_exists(pk)"}}]
    for a in registro["assignments"]:
        acoes.append({"Update": {
            "TableName": nome, "Key": {"pk": f"TEAM#{tid}", "sk": f"WEIGHT#{a['task']}#{a['person']}"},
            "UpdateExpression": "ADD cnt :um SET last_week = :s",
            "ExpressionAttributeValues": {":um": 1, ":s": semana}}})
    client = tabela().meta.client
    try:
        client.transact_write_items(TransactItems=acoes)
        return True
    except client.exceptions.TransactionCanceledException as e:
        if _cancelada_por_condicao(e):
            return False
        raise


def reverter_sorteio(tid, sorteio):
    """Transacao: remove o DRAW e decrementa os contadores."""
    nome = tabela().name
    acoes = [{"Delete": {"TableName": nome, "Key": {"pk": sorteio["pk"], "sk": sorteio["sk"]},
                         "ConditionExpression": "attribute_exists(pk)"}}]
    for a in sorteio["assignments"]:
        acoes.append({"Update": {
            "TableName": nome, "Key": {"pk": f"TEAM#{tid}", "sk": f"WEIGHT#{a['task']}#{a['person']}"},
            "UpdateExpression": "ADD cnt :menos", "ConditionExpression": "cnt >= :um",
            "ExpressionAttributeValues": {":menos": -1, ":um": 1}}})
    tabela().meta.client.transact_write_items(TransactItems=acoes)


def atualizar_sorteio(tid, semana, **campos):
    """AP-6: atualiza campos de controle do DRAW (status, sent_at, ...)."""
    nomes = {f"#{k}": k for k in campos}
    valores = {f":{k}": v for k, v in campos.items()}
    tabela().update_item(
        Key={"pk": f"TEAM#{tid}", "sk": f"DRAW#{semana}"},
        UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in campos),
        ExpressionAttributeNames=nomes, ExpressionAttributeValues=_dec(valores))


def aplicar_ops(tid, ops):
    """Aplica o plano de roster.planejar. Idempotente: pode ser reexecutado apos falha parcial."""
    pk = f"TEAM#{tid}"
    t = tabela()
    for op in ops:
        if op["op"] == "team":
            t.put_item(Item={"pk": "TEAMS", "sk": f"TEAM#{tid}", "v": V, **op["item"]})
        elif op["op"] in ("person", "task"):
            t.put_item(Item={"pk": pk, "sk": f"{op['op'].upper()}#{op['id']}", "v": V, **op["item"]})
        elif op["op"] == "deactivate":
            t.update_item(Key={"pk": pk, "sk": f"{op['kind'].upper()}#{op['id']}"},
                          UpdateExpression="SET active = :f, left_at = :l",
                          ExpressionAttributeValues={":f": False, ":l": op["left_at"]})
        elif op["op"] == "weight":
            item = {"pk": pk, "sk": f"WEIGHT#{op['task']}#{op['person']}", "cnt": 0, "v": V}
            if op["reset"]:
                t.put_item(Item=item)
            else:
                try:
                    t.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
                except t.meta.client.exceptions.ConditionalCheckFailedException:
                    pass  # ja existe: preserva o historico
