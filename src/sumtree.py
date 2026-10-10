"""Arvore de soma (roleta ponderada com pesos dinamicos). Puro, sem I/O."""


class SumTree:
    """Folhas = pesos; nos internos = soma dos filhos. set/sample em O(log n)."""

    def __init__(self, pesos):
        self.n = len(pesos)
        size = 1
        while size < self.n:
            size *= 2
        self.size = size
        self.t = [0.0] * (2 * size)
        for i, w in enumerate(pesos):
            self.t[size + i] = float(w)
        for i in range(size - 1, 0, -1):
            self.t[i] = self.t[2 * i] + self.t[2 * i + 1]

    def set(self, i, valor):
        i += self.size
        self.t[i] = float(valor)
        i //= 2
        while i:
            self.t[i] = self.t[2 * i] + self.t[2 * i + 1]
            i //= 2

    def total(self):
        return self.t[1]

    def peso(self, i):
        return self.t[self.size + i]

    def sample(self, u):
        """u em [0, total). Nunca devolve folha de peso 0 se total() > 0."""
        i = 1
        while i < self.size:
            esq = self.t[2 * i]
            if u < esq:
                i = 2 * i
            else:
                u -= esq
                i = 2 * i + 1
        i -= self.size
        if self.t[self.size + i] <= 0.0:  # guarda contra arredondamento na fronteira
            i = max(j for j in range(self.n) if self.t[self.size + j] > 0.0)
        return i
