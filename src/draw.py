"""Sorteio atomico por roleta inversa com arvore de soma. Puro, sem I/O.

Ver specs/001-sorteio-semanal/algoritmo.md.
"""

import random
from collections import Counter

from solver import resolver
from sumtree import SumTree


def peso(h):
    """Peso de sorteio: inverso da frequencia."""
    return 1.0 / (1 + h)


def sortear(pessoas, tarefas, h, prev, semente, max_tentativas=200):
    """pessoas, tarefas: listas de ids (ordem estavel).
    h: {(pessoa, tarefa): contador}; ausente = 0.
    prev: {tarefa: pessoa que a fez no sorteio anterior}.

    Devolve dict com mode/attempts/min_violations/seed/n/m/assignments
    (assignments[i] = {task, person, p, w, pool}), ou None se nao ha o que sortear.
    """
    n, m = len(pessoas), len(tarefas)
    if n == 0 or m == 0:
        return None
    idx = {p: i for i, p in enumerate(pessoas)}
    prev_i = [idx.get(prev.get(t)) for t in tarefas]
    lmin, lmax = m // n, -(-m // n)
    w = [[peso(h.get((p, t), 0)) for p in pessoas] for t in tarefas]
    k, otima = resolver(n, m, prev_i, lmin, lmax)

    for tentativa in range(1, max_tentativas + 1):
        atrib = _tentar(n, m, w, prev_i, lmin, lmax, k, random.Random(f"{semente}:{tentativa}"))
        if atrib is not None and _validar(atrib, n, m, prev_i, lmin, lmax, k):
            modo = "strict" if k == 0 else "relaxed"
            return _montar(pessoas, tarefas, atrib, modo, tentativa, k, semente, n, m)

    # Fallback deterministico (raro): atribuicao otima do solver, probabilidade nominal.
    atrib = {t: (p, w[t][p], sum(w[t])) for t, p in enumerate(otima)}
    return _montar(pessoas, tarefas, atrib, "fallback", max_tentativas, k, semente, n, m)


def _tentar(n, m, w, prev_i, lmin, lmax, k, rng):
    """Uma tentativa completa. Devolve {t: (p, w, pool)} ou None (= reverter)."""
    arvores = [SumTree(w[t]) for t in range(m)]
    for t in range(m):
        if prev_i[t] is not None:
            arvores[t].set(prev_i[t], 0.0)  # P1 como peso zero
    carga = [0] * n
    pend = set(range(m))
    violacoes = 0
    atrib = {}

    def deficit():
        return sum(max(0, lmin - c) for c in carga)

    ordem = list(range(m))
    rng.shuffle(ordem)
    for t in ordem:
        if deficit() == len(pend):  # piso forcado
            for tt in pend:
                for p in range(n):
                    if carga[p] >= lmin:
                        arvores[tt].set(p, 0.0)
        arv = arvores[t]
        if arv.total() <= 0.0:
            pv = prev_i[t]
            if violacoes < k and pv is not None and carga[pv] < lmax:
                arv.set(pv, w[t][pv])  # relaxamento controlado de P1
                violacoes += 1
            else:
                return None  # beco sem saida -> reverter a tentativa inteira
        pool = arv.total()
        p = arv.sample(rng.random() * pool)
        atrib[t] = (p, arv.peso(p), pool)
        carga[p] += 1
        pend.discard(t)
        if carga[p] >= lmax:
            for tt in pend:
                arvores[tt].set(p, 0.0)  # P2 (teto)
        if deficit() > len(pend):
            return None
    return atrib


def _validar(atrib, n, m, prev_i, lmin, lmax, k):
    """Unica autoridade sobre o que e um sorteio aceitavel (C0, P2 e P1 == k*)."""
    if len(atrib) != m:
        return False
    cargas = Counter(p for p, _w, _pool in atrib.values())
    if any(not (lmin <= cargas.get(p, 0) <= lmax) for p in range(n)):
        return False
    return sum(1 for t in range(m) if atrib[t][0] == prev_i[t]) == k


def _montar(pessoas, tarefas, atrib, modo, tentativas, k, semente, n, m):
    return {
        "mode": modo,
        "attempts": tentativas,
        "min_violations": k,
        "seed": str(semente),
        "n": n,
        "m": m,
        "assignments": [
            {
                "task": tarefas[t],
                "person": pessoas[atrib[t][0]],
                "p": atrib[t][1] / atrib[t][2],
                "w": atrib[t][1],
                "pool": atrib[t][2],
            }
            for t in range(m)
        ],
    }
