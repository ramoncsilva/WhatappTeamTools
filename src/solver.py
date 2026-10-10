"""Solver exato de k* (violacoes minimas de P1) por fluxo de custo minimo. Puro."""

from collections import deque

INF = float("inf")


def resolver(n, m, prev, lmin, lmax):
    """prev[t] = indice da pessoa que fez t antes, ou None.

    Devolve (k, atribuicao) onde atribuicao[t] = indice da pessoa, com cargas em
    [lmin, lmax] e o menor numero k de tarefas t com atribuicao[t] == prev[t].
    """
    big = m + 1  # priorizar o piso de carga sobre qualquer economia de violacoes
    src, dst = 0, m + n + 1
    g = [[] for _ in range(m + n + 2)]

    def add(u, v, cap, custo):
        g[u].append([v, cap, custo, len(g[v])])
        g[v].append([u, 0, -custo, len(g[u]) - 1])

    for t in range(m):
        add(src, 1 + t, 1, 0)
        for p in range(n):
            add(1 + t, 1 + m + p, 1, 1 if prev[t] == p else 0)
    for p in range(n):
        if lmin:
            add(1 + m + p, dst, lmin, -big)
        if lmax > lmin:
            add(1 + m + p, dst, lmax - lmin, 0)

    for _ in range(m):
        dist = [INF] * len(g)
        via = [None] * len(g)
        na_fila = [False] * len(g)
        dist[src] = 0
        fila = deque([src])
        while fila:
            u = fila.popleft()
            na_fila[u] = False
            for idx, (v, cap, custo, _rev) in enumerate(g[u]):
                if cap > 0 and dist[u] + custo < dist[v]:
                    dist[v] = dist[u] + custo
                    via[v] = (u, idx)
                    if not na_fila[v]:
                        na_fila[v] = True
                        fila.append(v)
        if dist[dst] == INF:
            raise ValueError("instancia inviavel: n * lmax < m")
        v = dst
        while v != src:
            u, idx = via[v]
            aresta = g[u][idx]
            aresta[1] -= 1
            g[v][aresta[3]][1] += 1
            v = u

    atrib = [None] * m
    for t in range(m):
        for v, cap, _custo, _rev in g[1 + t]:
            if v > m and cap == 0:  # aresta tarefa->pessoa saturada
                atrib[t] = v - m - 1
    k = sum(1 for t in range(m) if atrib[t] == prev[t])
    return k, atrib
