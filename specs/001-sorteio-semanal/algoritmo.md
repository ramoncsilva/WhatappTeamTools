# Algoritmo de sorteio — Roleta inversa com árvore de soma

Especificação do núcleo **puro** (sem I/O) da Lambda. Requisitos cobertos: FR-10 a FR-18, FR-21.

## 1. Notação

| Símbolo | Significado |
|---|---|
| `P`, `n = |P|` | pessoas **ativas** do time |
| `T`, `m = |T|` | tarefas **ativas** do time |
| `h(p,t)` | contador histórico (quantas vezes `p` já fez `t`); ausente ⇒ 0 |
| `w(p,t)` | peso de sorteio `= 1 / (1 + h(p,t))` |
| `prev(t)` | pessoa que exerceu `t` no **último sorteio existente** do time; indefinida se não houve, ou se saiu do time |
| `Lmin = ⌊m/n⌋`, `Lmax = ⌈m/n⌉` | carga mínima e máxima por pessoa |
| `k*` | nº **mínimo** de violações de P1 entre todas as atribuições válidas (§5) |

## 2. Peso: inverso da frequência

```
w(p,t) = 1 / (1 + h(p,t))
```

| h | 0 | 1 | 2 | 3 | 5 | 9 |
|---|---|---|---|---|---|---|
| w | 1 | 0,5 | 0,333 | 0,25 | 0,167 | 0,1 |

- Quem **nunca** fez a tarefa tem o peso máximo (`w = 1`); o peso cai monotonicamente com a frequência e **nunca chega a zero**, então ninguém é excluído apenas por já ter feito a tarefa muitas vezes.
- **Pessoa nova** ⇒ `h = 0` em toda tarefa ⇒ `w = 1`. Confirmado pelo solicitante (ver [spec.md §10](spec.md#10-premissas-adotadas-e-pontos-a-confirmar)): o valor *armazenado* ("peso zero" do pedido original) é o histórico zero; o *peso de sorteio* é o mais alto.
- A `+1` no denominador evita divisão por zero e mantém `w ∈ (0, 1]`.

## 3. Árvore de soma

Estrutura sobre `n` folhas (uma por pessoa), em array (heap implícito, tamanho `2·N`, `N` = menor potência de 2 ≥ `n`):

| Operação | Efeito | Custo |
|---|---|---|
| `build(pesos)` | folhas = pesos, nós internos = soma dos filhos | O(n) |
| `set(i, v)` | altera a folha `i` e reajusta os ancestrais | O(log n) |
| `total()` | soma de todos os pesos (raiz) | O(1) |
| `sample(u)` com `u ∈ [0, total)` | desce da raiz: se `u < esquerda` vai à esquerda, senão `u -= esquerda` e vai à direita; retorna a folha | O(log n) |

- `set(i, 0)` torna a pessoa **inelegível** (peso zero ⇒ probabilidade zero) sem reconstruir a árvore — é assim que os pesos são "dinâmicos".
- `sample` nunca retorna folha de peso 0 se `total() > 0`.
- **Probabilidade** de `p` ser escolhida = `peso(p) / total()` no instante da escolha.
- Existe **uma árvore por tarefa** (os pesos `w(·,t)` diferem por tarefa), construídas a cada tentativa.
- Aritmética em `float` (suficiente para n ≤ 50); a semente fixa o resultado, então o sorteio é reproduzível.

> Para `n ≤ 8` (limite de um grupo da Meta) uma varredura linear daria o mesmo resultado. A árvore é mantida por **requisito do modelo** e porque o custo é desprezível; ela garante O(log n) se o time crescer.

## 4. Restrições

Uma **atribuição** é uma função `α : T → P`. É **válida** se:

| ID | Restrição | Natureza |
|---|---|---|
| **C0** Cobertura | toda tarefa de `T` tem exatamente uma pessoa | dura |
| **P2** Carga | para todo `p`: `Lmin ≤ |α⁻¹(p)| ≤ Lmax` | dura |
| **P1** Não repetição | para todo `t` com `prev(t)` definida: `α(t) ≠ prev(t)` | dura **enquanto possível** |

Consequências de P2: se `m ≤ n`, `Lmax = 1` e `Lmin = 0` (cada pessoa no máximo 1 tarefa); se `m > n`, `Lmin ≥ 1` — **todos** trabalham e a carga é equilibrada (`{⌊m/n⌋, ⌈m/n⌉}`). Acumular só ocorre quando `m > n`, como exige a Premissa 2.

**Ordem de prioridade ao relaxar:** C0 > P2 > P1. P1 é a única cedida, e só no mínimo necessário.

## 5. Viabilidade e solver exato

`k*` é o menor nº de tarefas `t` com `α(t) = prev(t)` entre todas as atribuições que satisfazem C0 e P2.

- **`k* = 0`** ⇒ P1 é respeitável; o sorteio **deve** respeitá-la.
- **`k* > 0`** ⇒ P1 é *provadamente impossível* ("falta de pessoas ou excesso de tarefas"); o sorteio deve violá-la **exatamente `k*` vezes**.
- Sempre existe atribuição com C0 e P2 (ignorando P1), logo o sorteio nunca fica sem resposta.

O solver é um **fluxo de custo mínimo** num grafo bipartido pequeno (n, m ≤ ~50): `fonte → tarefa (cap 1)`, `tarefa → pessoa (cap 1, custo 1 se pessoa = prev(tarefa), senão 0)`, `pessoa → destino (cap `Lmax`, com `Lmin` unidades obrigatórias)`. Detalhe de implementação em [plan.md §6](plan.md#6-módulos-da-lambda). Ele serve a **dois** fins: calcular `k*` e fornecer o fallback determinístico (§6, passo 4).

## 6. Procedimento do sorteio (atômico)

```
sortear(time, h, prev, semente, max_tentativas) -> Sorteio
  n, m ← |P|, |T|;  se n = 0 ou m = 0: retornar VAZIO
  Lmin, Lmax ← ⌊m/n⌋, ⌈m/n⌉
  k*, otima ← solver(P, T, prev, Lmin, Lmax)                       # §5

  para tentativa em 1..max_tentativas:                              # 1) sortear
      rng ← Random(semente, tentativa)
      arvore[t] ← build( w(p,t) para p em P )          para todo t em T
      carga[p] ← 0;  violacoes ← 0;  atrib ← {}
      para todo t com prev(t) definida: arvore[t].set(prev(t), 0)   # P1 como peso zero

      para t em permutacao_aleatoria(T, rng):
          se Σ_p max(0, Lmin − carga[p]) = tarefas_pendentes:       # PISO FORÇADO (ver abaixo)
              para todo t' pendente e todo p com carga[p] ≥ Lmin: arvore[t'].set(p, 0)
          se arvore[t].total() = 0:                                 # sem candidato estrito
              se violacoes < k* e prev(t) definida e carga[prev(t)] < Lmax:
                  arvore[t].set(prev(t), w(prev(t), t));  violacoes += 1   # relaxamento controlado
              senão: → REVERTER tentativa                           # beco sem saída
          p ← arvore[t].sample( rng.random() * arvore[t].total() )
          prob ← arvore[t].peso(p) / arvore[t].total()              # probabilidade exibida
          atrib[t] ← (p, prob);  carga[p] += 1
          se carga[p] = Lmax: para todo t' pendente: arvore[t'].set(p, 0)   # P2 (teto)
          se Σ_p max(0, Lmin − carga[p]) > tarefas_restantes: → REVERTER tentativa   # P2 (piso)

      se validar(atrib) = OK: retornar Sorteio(atrib, modo, tentativa)
      # senão: REVERTER (descartar atrib, carga, arvores — nada foi gravado)

  # 2) esgotadas as tentativas (raríssimo): fallback determinístico
  retornar Sorteio(otima, "fallback", max_tentativas)               # + justificativa J3
```

`validar(atrib)` é a **única** autoridade sobre o que é um sorteio aceitável:

1. C0: toda tarefa tem dono;
2. P2: toda carga em `[Lmin, Lmax]`;
3. P1: nº de tarefas com `α(t) = prev(t)` **igual a `k*`**.

`modo` ∈ { `strict` (`k* = 0`), `relaxed` (`k* > 0`), `fallback` }.

### Reversão automática — definição precisa
"Reverter" = **descartar todo o estado da tentativa** (atribuições parciais, cargas, árvores) e começar outra com `tentativa + 1`. Como o estado só vive em memória até `validar` passar, **nenhum dado parcial é persistido** (FR-14/FR-16). A gravação acontece uma única vez, depois, numa transação (data-model.md §5).

### Piso forçado (regra de elegibilidade de P2)
Quando a soma dos *déficits* (`Σ max(0, Lmin − carga[p])`) iguala o número de tarefas ainda pendentes, **só quem está abaixo do piso pode receber** as tarefas restantes; os demais têm o peso zerado nas árvores pendentes. Se esse conjunto restrito estiver vazio por causa de P1, aplica-se o relaxamento (`violacoes < k*`).

Sem essa regra o sorteio só descobria o piso violado *depois* de escolher, revertia, e nunca relaxava P1 — caindo no fallback determinístico. Num protótipo descartável (4 000 instâncias aleatórias, n ≤ 5, m ≤ 6, comparado com força bruta):

| Variante | Fallback | Inválidos | Tentativas (mediana / p99 / máx.) |
|---|---|---|---|
| sem piso forçado | 189 (4,7 %) | 0 | 1 / 200 / 200 |
| **com piso forçado** | **0** | **0** | **1 / 2 / 6** |

Cenário típico que ela resolve: a pessoa A fez *todas* as tarefas quando estava sozinha; agora o time tem B e C. P2 exige que A faça ao menos uma (`Lmin ≥ 1`) e A é `prev` de todas ⇒ `k* = 1`, e a violação precisa ocorrer na última tarefa, mesmo havendo "candidato" aparente.

### Por que sortear a ordem das tarefas
Uma ordem fixa daria vantagem sistemática às primeiras tarefas (escolhem entre mais candidatos). A permutação aleatória por tentativa remove esse viés; o custo é possíveis becos sem saída — resolvidos pela reversão.

## 7. Probabilidade exibida

`prob(t) = w(p,t) / Σ_{q elegível} w(q,t)` **no instante da escolha de `t`**, isto é, condicionada às tarefas já sorteadas nessa tentativa (que podem ter removido candidatos por P2) e às exclusões de P1.

- É a "chance de sorteio atrelada" pedida; é exata para a tentativa aceita e totalmente explicável.
- **Não** é a probabilidade marginal sobre todas as ordens e tentativas possíveis; a mensagem diz "chance no momento do sorteio".
- Guarda-se também `pool = Σ w` e `w` do escolhido, para auditoria.

## 8. Atualização do peso histórico

Após o sorteio ser gravado: `h(α(t), t) += 1` para cada `t`. Nada mais muda. Reverter um sorteio faz `-1` nos mesmos pares.

## 9. Justificativas

Geradas a partir do resultado final (função pura `justificar(sorteio, contexto)`):

| Código | Condição | Texto (pt-BR) |
|---|---|---|
| **J1** | pessoa com `carga > 1` | `{pessoa} ficou com {c} tarefas: há mais tarefas ({m}) do que pessoas ({n}).` |
| **J2** | `α(t) = prev(t)` | `{pessoa} repete "{tarefa}" da semana passada: não havia outra pessoa elegível.` |
| **J3** | `modo = fallback` | `Sorteio resolvido por atribuição determinística após {N} tentativas.` |
| **J4** | pessoa cuja entrada (`joined_at`) é posterior ao sorteio anterior do time | `{pessoa} entrou no time esta semana e começa com chance máxima.` *(informativa)* |

J1–J3 explicam **exceções às premissas**; J4 é informativa. Sem exceções, a mensagem não traz bloco de justificativas (exceto J4, se houver).

## 10. Exemplo numérico

Time com `n = 4` (Ana, Bruno, Carla, Diego) e `m = 3` tarefas ⇒ `Lmin = 0`, `Lmax = 1`.
Último sorteio: Ata → Carla, Café → Ana, Limpeza → Bruno. `k* = 0`.

Contadores `h`:

| | Ana | Bruno | Carla | Diego |
|---|---|---|---|---|
| Ata | 2 | 0 | 1 | 3 |
| Café | 1 | 0 | 0 | 2 |
| Limpeza | 0 | 3 | 1 | 1 |

Ordem sorteada: Ata → Café → Limpeza.

**Ata** (`prev` = Carla ⇒ peso 0):

| Pessoa | h | w | elegível | prob |
|---|---|---|---|---|
| Ana | 2 | 1/3 | sim | (1/3)/(19/12) = 4/19 = **21,1 %** |
| Bruno | 0 | 1 | sim | 12/19 = **63,2 %** |
| Carla | 1 | 1/2 | **não** (P1) | 0 |
| Diego | 3 | 1/4 | sim | 3/19 = **15,8 %** |

Total `= 1/3 + 1 + 1/4 = 19/12`. Sai **Bruno** (63,2 %); `carga[Bruno] = 1 = Lmax` ⇒ peso 0 nas demais árvores.

**Café** (`prev` = Ana; Bruno já no teto): elegíveis Carla (`w = 1`) e Diego (`w = 1/3`), total `4/3` ⇒ Carla **75,0 %**, Diego 25,0 %. Sai **Carla**.

**Limpeza** (`prev` = Bruno; Bruno e Carla no teto): elegíveis Ana (`w = 1`) e Diego (`w = 1/2`), total `3/2` ⇒ Ana **66,7 %**, Diego 33,3 %. Sai **Ana**.

Resultado: Ata → Bruno (63,2 %) · Café → Carla (75,0 %) · Limpeza → Ana (66,7 %); Diego sem tarefa (`m < n`). Nenhuma justificativa de exceção.

**Exemplo com sobreposição (`n = 2`, `m = 3`)**: `Lmin = 1`, `Lmax = 2` ⇒ cargas {2, 1}; quem pega 2 recebe J1. Se, além disso, `prev` impuser que a mesma pessoa repita uma tarefa (`k* = 1`), o modo é `relaxed` e entra J2.

## 11. Invariantes e testes de propriedade

Para **qualquer** entrada válida (gerada aleatoriamente com semente fixa), o resultado satisfaz:

| ID | Invariante |
|---|---|
| INV-1 | Toda tarefa ativa tem exatamente uma pessoa ativa. |
| INV-2 | Toda carga está em `[Lmin, Lmax]`; se `m ≤ n`, ninguém tem 2 tarefas. |
| INV-3 | O nº de violações de P1 é igual a `k*`; se `k* = 0`, nenhuma. |
| INV-4 | `k*` é mínimo (conferido contra força bruta para `n, m ≤ 6`). |
| INV-5 | `prob ∈ (0, 1]` e, para cada tarefa, `prob = w(p,t)/pool` dentro de 1e-9. |
| INV-6 | Mesmos `(estado, semente)` ⇒ mesmo sorteio. |
| INV-7 | Nenhum `w` zero é amostrado (a árvore nunca retorna peso 0 com `total > 0`). |
| INV-8 | Distribuição: com `n=2`, `m=1`, `h=(0,3)` e sem P1, a frequência empírica de `p0` converge a `1/(1+0,25)=80 %` (±2 p.p. em 10⁵ amostras). |
| INV-9 | `sample` com `u` em todas as fronteiras de intervalo cai na folha correta (teste unitário da árvore). |
| INV-10 | O fallback é raro: em ≥ 4 000 instâncias aleatórias (n ≤ 5, m ≤ 6, incluindo `prev` idêntico para todas as tarefas), `fallback = 0` e `tentativas ≤ 10`. |
