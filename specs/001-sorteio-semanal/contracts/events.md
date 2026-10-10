# Contrato — eventos da Lambda e arquivo de cadastro

A Lambda tem **um** ponto de entrada (`index.handler`) e despacha pelo campo `action`. Ausente ⇒ `weekly`.
Requisitos: FR-04, FR-30, FR-31, FR-32, FR-42.

## 1. `weekly` — sorteia e envia (padrão do agendamento)

```json
{ "action": "weekly", "team": "plataforma", "week": "2026-W42", "dry_run": false }
```

| Campo | Tipo | Padrão | Descrição |
|---|---|---|---|
| `team` | string (slug) | todos os times ativos | Restringe a um time. |
| `week` | `YYYY-Www` | semana ISO atual no fuso do time | Ciclo do sorteio. |
| `dry_run` | bool | `false` | Sorteia e renderiza a mensagem, mas **não grava nem envia**. |

Fluxo por time (isolado dos demais, FR-24):

```
carregar time (AP-2) ─► DRAW da semana existe? (AP-4)
   ├─ sim, SENT     ─► SKIPPED (idempotente)
   ├─ sim, PENDING  ─► reenviar (sem sortear)                     ─► SENT | falha
   └─ não           ─► carregar sorteio anterior (AP-3) ─► sortear ─► (dry_run? retornar)
                        ─► gravar transação (§5.1 do data-model)    ─► enviar ─► SENT | PENDING
```

**Resposta** (sempre JSON; falha de qualquer time ⇒ a Lambda lança exceção *depois* de processar todos):

```json
{
  "ok": true,
  "teams": [
    { "team": "plataforma", "week": "2026-W42", "status": "SENT",
      "mode": "strict", "attempts": 3, "assignments": 3 }
  ]
}
```

| `status` | Significado |
|---|---|
| `SENT` | Sorteio gravado e mensagem enviada. |
| `PENDING` | Sorteio gravado; envio falhou (`error` explica). Exceção ao final. |
| `SKIPPED` | Já estava `SENT`, ou time sem pessoas/tarefas (`reason`: `already_sent` \| `no_people` \| `no_tasks`). |
| `DRY_RUN` | Nada gravado/enviado; traz `message` (texto que seria enviado) e `assignments` detalhadas. |
| `ERROR` | Falha antes de gravar (ex.: `no_group_id`, banco indisponível). Exceção ao final. |

## 2. `resend` — reenvia um sorteio já gravado

```json
{ "action": "resend", "team": "plataforma", "week": "2026-W42" }
```
Reenvia o `DRAW` existente (qualquer status) **sem** sortear e sem tocar nos contadores. Atualiza `status`, `send_attempts`, `sent_at`, `wa_message_id`. Erro se o sorteio não existir.

## 3. `revert` — desfaz o último sorteio *(Should)*

```json
{ "action": "revert", "team": "plataforma" }
```
Desfaz o **sorteio mais recente** do time (§5.2 do data-model): remove o `DRAW` e decrementa os contadores, numa transação. Depois disso `weekly` pode sortear a mesma semana de novo (com nova semente). Não recolhe a mensagem já enviada ao WhatsApp (a API não permite apagar). Resposta: `{ "ok": true, "reverted": "2026-W42", "decremented": 3 }`.

## 4. `sync_roster` — sincroniza o cadastro

```json
{ "action": "sync_roster", "dry_run": false, "roster": { "teams": [ /* ver §5 */ ] } }
```

Aplica o estado declarado em `roster` (regras em data-model.md §5.3). **Idempotente.** Resposta:

```json
{
  "ok": true, "dry_run": false,
  "teams": [
    { "team": "plataforma",
      "created":     { "people": ["eva"], "tasks": [] },
      "reactivated": { "people": [], "tasks": [] },
      "deactivated": { "people": ["diego"], "tasks": [] },
      "updated":     { "team": false, "people": [], "tasks": [] },
      "weights_created": 3 }
  ]
}
```
Times ausentes de `roster` **não** são alterados (o arquivo pode descrever só parte). Para inativar um time, declare-o com `"active": false`.

## 5. Arquivo de cadastro (`data/roster.json`)

Exemplo: [../../../data/roster.example.json](../../../data/roster.example.json).

```jsonc
{
  "teams": [{
    "id": "plataforma",                    // slug [a-z0-9-]{1,40}, imutável
    "name": "Plataforma",                  // 1–60 chars
    "whatsapp_group_id": "Y2FwaV9ncm91cDo…", // opaco, devolvido pela Groups API; vazio ⇒ time não envia
    "timezone": "America/Sao_Paulo",       // IANA; padrão America/Sao_Paulo
    "active": true,                        // padrão true
    "people": [ { "id": "ana", "name": "Ana" } ],     // id slug imutável; name 1–60
    "tasks":  [ { "id": "ata", "name": "Ata da daily" } ]   // máx. 99 por time
  }]
}
```

**Validação** (falha tudo-ou-nada antes de gravar qualquer coisa; mensagem aponta o caminho do campo):
- `id` único dentro do escopo (times globais; pessoas/tarefas por time) e no formato slug;
- `name` não vazio, sem quebras de linha;
- `timezone` válido; ≤ 99 tarefas por time (limite da transação);
- **aviso** (não erro) se `people > 7`: grupo da Meta comporta no máximo 8 participantes, incluindo o número da empresa.

## 6. Erros e retentativas

- Erros de validação/uso (`action` desconhecida, `team` inexistente, JSON inválido) ⇒ exceção imediata (sem retry útil).
- Invocação assíncrona do agendador: 2 retries da Lambda + 3 do Scheduler; esgotados ⇒ SNS (e-mail). Tudo é idempotente, então repetir é seguro.
- A resposta e os logs **nunca** contêm o token da Meta.
