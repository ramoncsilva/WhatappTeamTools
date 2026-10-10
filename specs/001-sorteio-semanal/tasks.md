# Tarefas

Ordem de execução. `[P]` = pode rodar em paralelo com as outras tarefas `[P]` da mesma fase.
Estado: `[x]` entregue **e verificado por testes automatizados** (26 testes, `tests/`); `[~]` arquivo criado mas **ainda não exercitado** contra a AWS; `[ ]` a fazer.

## Fase 0 — Validação externa (bloqueia a Fase 3, tarefa T-23)

- [ ] **T-00 Spike Meta/WhatsApp** — verificar elegibilidade (OBA), criar o grupo pela Groups API, entrar pelo link de convite, obter o `group id`, enviar **texto livre** com a janela fechada e aberta, registrar o código de erro retornado, criar/aprovar o template `sorteio_semanal` e testar o formato compacto (sem `\n`). Resultado: preencher os itens **[validar T-00]** de [contracts/whatsapp.md](contracts/whatsapp.md) e a decisão do §10.3 da spec (grupo × mensagem individual).
  *DoD:* uma mensagem real chegou ao grupo; contrato atualizado.

## Fase 1 — Infraestrutura e sincronização (entregue com esta spec)

- [~] **T-01 Template CloudFormation** — [infra/template.yaml](../../infra/template.yaml). *Req:* FR-40, NFR-02, AC-13.
- [~] **T-02 Configuração por `.properties`** — [config/app.properties.example](../../config/app.properties.example), `.gitignore`. *Req:* C-3, AC-12.
- [~] **T-03 Scripts de sincronização** — [scripts/](../../scripts/) (`common`, `deploy`, `sync-roster`, `invoke`). *Req:* FR-41, FR-42, AC-14.
- [ ] **T-04 Primeiro deploy do esqueleto** — rodar `deploy.ps1 -SkipCode` numa conta real; conferir recursos, e-mail do SNS, parâmetro SSM `SecureString`. *DoD:* stack `CREATE_COMPLETE`; `aws ssm get-parameter` **sem** `--with-decryption` não exibe o token.
- [x] **T-05 Teste estático do template** `[P]` — `cfn-lint` + teste que falha se aparecer tipo de recurso fora da lista de [plan.md §2](plan.md#2-recursos-aws-e-free-tier) ou a palavra `secret` com valor. *Req:* AC-12, AC-13.

## Fase 2 — Núcleo puro (TDD; sem rede nem AWS)

- [x] **T-10 `sumtree.py`** `[P]` — `build/set/total/sample/peso`. *Testes:* INV-7, INV-9. *Req:* FR-11.
- [x] **T-11 `solver.py`** `[P]` — `k*` e atribuição ótima (fluxo de custo mínimo). *Testes:* INV-4 contra força bruta (n, m ≤ 6). *Req:* FR-13, FR-15.
- [x] **T-12 `draw.py`** *(depende de T-10, T-11)* — `sortear()` e `validar()` de [algoritmo.md §6](algoritmo.md#6-procedimento-do-sorteio-atômico). Inclui a regra do **piso forçado**. *Testes:* INV-1…INV-10; AC-01, 02, 03, 04, 06, 07. *Req:* FR-10…FR-15, FR-18.
- [x] **T-13 `message.py`** `[P]` — `justificar()` (J1–J4) e `renderizar()` (texto + compacto + divisão em partes), sanitização de nomes. *Testes:* *golden files* dos exemplos de [contracts/whatsapp.md](contracts/whatsapp.md); caso > 4096 caracteres. *Req:* FR-20, FR-21.
- [x] **T-14 `roster.py` (parte pura)** `[P]` — `validar()` e `planejar()` (diff: criar/reativar/inativar, pesos zero). *Testes:* AC-05, AC-10 sobre o plano. *Req:* FR-03, FR-04.

## Fase 3 — Bordas (I/O)

- [x] **T-20 `store.py`** — AP-1…AP-6, `commit_draw` (transação + condição), `revert_draw`, `apply_roster_plan`. *Testes:* *fake* em memória + (opcional) DynamoDB Local. *Req:* FR-16, FR-17, FR-32; AC-08.
- [x] **T-21 `config.py`** — variáveis de ambiente + token do SSM com cache. *Req:* NFR-03.
- [x] **T-22 `index.py`** — roteamento de ações, isolamento por time, resposta agregada, exceção final, `dry_run`, logs JSON sem nomes. *Req:* FR-24, FR-30, FR-31; AC-11.
- [~] **T-23 `whatsapp.py`** *(depende de T-00)* — envio texto/template, modo `auto`, classificação de erros, backoff, timeout 10 s. *Testes:* servidor HTTP local. *Req:* FR-22, FR-23; AC-09.

## Fase 4 — Integração

- [ ] **T-30 Deploy do código** — `deploy.ps1` completo; verificar pacote ≤ 100 KB e *cold start* < 1 s. *Req:* NFR-01, AC-14.
- [ ] **T-31 Roster real** — `sync-roster.ps1 -DryRun` e depois real; conferir itens no DynamoDB (contadores 0). *Req:* AC-10.
- [ ] **T-32 Ensaio ponta a ponta** — `invoke.ps1 -Action weekly -DryRun`; depois execução real num **grupo de teste**; repetir (idempotência, AC-08); forçar falha de token (AC-09); `revert` + novo `weekly`. *Req:* AC-08, AC-09, AC-11, FR-32.
- [ ] **T-33 Alerta de falha** — provocar erro e confirmar e-mail do SNS. *Req:* FR-33, US-8.
- [ ] **T-34 Conferir custo** — após 1 mês, Billing/Cost Explorer = **US$ 0,00** de AWS. *Req:* NFR-02.

## Fase 5 — Operação

- [ ] **T-40 Ativar o agendamento** no grupo real (`schedule.state=ENABLED`) e acompanhar a 1ª execução semanal.
- [ ] **T-41 Rotina de backup** — exportação mensal (`plan.md §8`).

## Rastreabilidade

| Requisito | Tarefas | Critérios |
|---|---|---|
| FR-01…04 | T-14, T-20, T-31 | AC-05, AC-10 |
| FR-10…15, FR-18 | T-10, T-11, T-12 | AC-01…04, AC-06, AC-07 |
| FR-16, FR-17, FR-32 | T-20, T-32 | AC-06, AC-08 |
| FR-20…23 | T-13, T-23, T-00 | AC-04, AC-09 |
| FR-24, FR-30, FR-31 | T-22, T-40 | AC-11 |
| FR-33 | T-01, T-33 | — |
| FR-40…42 | T-01, T-02, T-03, T-04 | AC-12, AC-13, AC-14 |
| NFR-01…08 | T-05, T-30, T-34 + testes das Fases 2–3 | AC-12, AC-13 |
