import itertools
import random
from collections import Counter

import pytest

from draw import sortear
from solver import resolver
from sumtree import SumTree


def test_sumtree_fronteiras_e_zero():
    t = SumTree([1.0, 0.5, 0.25])
    assert t.total() == pytest.approx(1.75)
    assert [t.sample(u) for u in (0.0, 0.999, 1.0, 1.4999, 1.5, 1.7499)] == [0, 0, 1, 1, 2, 2]
    t.set(1, 0.0)
    assert t.total() == pytest.approx(1.25)
    assert all(t.sample(u) != 1 for u in (0.0, 0.5, 1.0, 1.2499))


def test_sumtree_distribuicao_inv8():
    rng = random.Random(1)
    n = 100_000
    t = SumTree([1.0, 0.25])
    freq = sum(t.sample(rng.random() * t.total()) == 0 for _ in range(n)) / n
    assert abs(freq - 0.8) < 0.02


def _forca_bruta(n, m, prev, lmin, lmax):
    melhor = None
    for a in itertools.product(range(n), repeat=m):
        c = Counter(a)
        if any(not (lmin <= c.get(p, 0) <= lmax) for p in range(n)):
            continue
        v = sum(1 for t in range(m) if prev[t] == a[t])
        melhor = v if melhor is None else min(melhor, v)
    return melhor


def _instancia(R):
    n, m = R.randint(1, 5), R.randint(1, 6)
    estilo = R.choice(["rand", "igual", "nenhum"])
    if estilo == "rand":
        prev = [R.randrange(n) if R.random() < 0.9 else None for _ in range(m)]
    elif estilo == "igual":
        prev = [R.randrange(n)] * m
    else:
        prev = [None] * m
    return n, m, prev


def test_solver_k_minimo_contra_forca_bruta():
    R = random.Random(11)
    for _ in range(600):
        n, m, prev = _instancia(R)
        lmin, lmax = m // n, -(-m // n)
        k, atrib = resolver(n, m, prev, lmin, lmax)
        assert k == _forca_bruta(n, m, prev, lmin, lmax)
        c = Counter(atrib)
        assert all(lmin <= c.get(p, 0) <= lmax for p in range(n))


def test_invariantes_do_sorteio_e_fallback_raro():
    R = random.Random(7)
    modos = Counter()
    for i in range(1500):
        n, m, prev_i = _instancia(R)
        pessoas = [f"p{j}" for j in range(n)]
        tarefas = [f"t{j}" for j in range(m)]
        h = {(p, t): R.randint(0, 6) for p in pessoas for t in tarefas}
        prev = {tarefas[t]: pessoas[p] for t, p in enumerate(prev_i) if p is not None}
        r = sortear(pessoas, tarefas, h, prev, i)
        modos[r["mode"]] += 1
        lmin, lmax = m // n, -(-m // n)
        assert [a["task"] for a in r["assignments"]] == tarefas                      # INV-1
        c = Counter(a["person"] for a in r["assignments"])
        assert all(lmin <= c.get(p, 0) <= lmax for p in pessoas)                      # INV-2
        viol = sum(1 for a in r["assignments"] if prev.get(a["task"]) == a["person"])
        assert viol == r["min_violations"]                                            # INV-3
        for a in r["assignments"]:
            assert 0 < a["p"] <= 1 and a["p"] == pytest.approx(a["w"] / a["pool"])    # INV-5
        assert sortear(pessoas, tarefas, h, prev, i) == r                             # INV-6
    assert modos["fallback"] == 0                                                     # INV-10


def test_exemplo_numerico_da_spec():
    # algoritmo.md §10: probabilidade de Bruno para Ata = 12/19 quando Ata e a 1a tarefa sorteada
    pessoas, tarefas = ["ana", "bruno", "carla", "diego"], ["ata"]
    h = {("ana", "ata"): 2, ("bruno", "ata"): 0, ("carla", "ata"): 1, ("diego", "ata"): 3}
    probs = {}
    for seed in range(200):
        r = sortear(pessoas, tarefas, h, {"ata": "carla"}, seed)
        a = r["assignments"][0]
        assert a["person"] != "carla"
        probs[a["person"]] = a["p"]
    assert probs["bruno"] == pytest.approx(12 / 19)
    assert probs["ana"] == pytest.approx(4 / 19)
    assert probs["diego"] == pytest.approx(3 / 19)


def test_time_vazio():
    assert sortear([], ["t"], {}, {}, 1) is None
    assert sortear(["a"], [], {}, {}, 1) is None


def test_uma_pessoa_relaxa_p1():  # AC-07
    r = sortear(["ana"], ["a", "b"], {}, {"a": "ana", "b": "ana"}, 3)
    assert r["mode"] == "relaxed" and {x["person"] for x in r["assignments"]} == {"ana"}
