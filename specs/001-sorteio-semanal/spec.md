# Spec 001 — Sorteio semanal de tarefas do time via WhatsApp

| Campo | Valor |
|---|---|
| Status | **Aprovada para implementação do núcleo e da infraestrutura** — o envio ao WhatsApp aguarda a validação T-00 (seção 9 e ponto 3 da seção 10) |
| Data | 2026-10-10 |
| Documentos irmãos | [algoritmo.md](algoritmo.md) · [data-model.md](data-model.md) · [plan.md](plan.md) · [tasks.md](tasks.md) · [contracts/events.md](contracts/events.md) · [contracts/whatsapp.md](contracts/whatsapp.md) |
| Princípios | [../constitution.md](../constitution.md) |

---

## 1. Contexto e objetivo

Times pequenos dividem tarefas recorrentes (ata da daily, café, limpeza, plantão…). Sorteios manuais
são injustos (sempre os mesmos pegam) e pouco transparentes.

**Objetivo:** uma AWS Lambda que, toda semana, sorteia **de uma só vez** a pessoa responsável por **cada**
tarefa de **cada** time, usando uma roleta ponderada pelo **inverso da frequência** (quem fez menos tem
mais chance), respeitando duas premissas de justiça, e publica o resultado — com probabilidades e
justificativas — no grupo de WhatsApp do time pela API oficial da Meta.

## 2. Escopo

**Dentro:** modelo de dados, algoritmo de sorteio, execução semanal agendada, envio ao WhatsApp,
sincronização do cadastro (times/pessoas/tarefas), infraestrutura como código (CloudFormation) e scripts
de sincronização com a AWS, configuração de credenciais por arquivo `.properties`.

**Fora (v1):** interface web; receber/ler mensagens do WhatsApp (comandos no grupo); elegibilidade
por pessoa×tarefa (ex.: "Fulano não faz X"); trocas manuais de tarefa; múltiplos idiomas; mais de um
sorteio por semana; CI/CD em nuvem.

## 3. Glossário

| Termo | Definição |
|---|---|
| **Time** | Conjunto de pessoas e de tarefas, com um grupo de WhatsApp. |
| **Ciclo / semana** | Semana ISO (`2026-W42`) no fuso do time. Um sorteio por time por ciclo. |
| **n, m** | Nº de pessoas ativas e de tarefas ativas do time. |
| **h(p,t)** | *Peso histórico*: quantas vezes a pessoa `p` já foi sorteada para a tarefa `t`. É o número guardado no banco. |
| **w(p,t)** | *Peso de sorteio* = `1 / (1 + h(p,t))`. É o que alimenta a roleta. |
| **Árvore de soma** | Árvore binária cujos nós guardam a soma dos pesos das folhas; permite sortear e atualizar pesos em O(log n). |
| **Premissa 1 (P1)** | Ninguém é sorteado duas vezes seguidas para a mesma tarefa. |
| **Premissa 2 (P2)** | Ninguém acumula mais de uma tarefa, salvo se houver mais tarefas que pessoas. |
| **Reversão automática** | Descartar um sorteio inteiro (nada foi gravado) e sortear de novo quando ele viola P1/P2. |
| **Relaxamento** | Violar P1 o mínimo possível, só quando é *provadamente impossível* respeitá-la. |

## 4. Histórias de usuário

| ID | Como… | Quero… | Para… | Prioridade |
|---|---|---|---|---|
| US-1 | membro do time | receber toda semana no grupo quem cuida de cada tarefa | não precisar combinar manualmente | Must |
| US-2 | membro do time | ver a chance de cada escolha e o porquê de qualquer exceção | confiar que o sorteio é justo | Must |
| US-3 | membro do time | que quem fez menos uma tarefa tenha mais chance de pegá-la | a carga se equilibrar ao longo do tempo | Must |
| US-4 | administrador | cadastrar times, pessoas e tarefas num arquivo e sincronizar com a AWS | não editar banco à mão | Must |
| US-5 | administrador | que quem entra no time comece com histórico zero em todas as tarefas | a entrada não distorça o sorteio | Must |
| US-6 | administrador | reexecutar sem duplicar sorteio nem mensagem, e poder desfazer o último sorteio | recuperar-me de falhas | Must / Should |
| US-7 | administrador | subir toda a infraestrutura com um comando e sem custo | operar sem gastar | Must |
| US-8 | administrador | ser avisado por e-mail se a execução semanal falhar | o time não ficar sem sorteio | Should |

## 5. Requisitos funcionais

### Dados
- **FR-01** O sistema mantém **times**, **pessoas** e **tarefas**; cada pessoa e cada tarefa pertence a exatamente um time.
- **FR-02** Para cada par (pessoa, tarefa) do mesmo time existe um contador `h` (inteiro ≥ 0).
- **FR-03** Quando uma pessoa entra no time, são criados contadores `h = 0` para **todas** as tarefas do time. Quando uma tarefa é criada, são criados `h = 0` para todas as pessoas. *Reentrada* (pessoa inativa que volta) conta como entrada: seus contadores voltam a 0.
- **FR-04** O cadastro é sincronizado de forma **declarativa e idempotente** a partir de um arquivo JSON. Quem sai do arquivo é **inativado**, nunca apagado (preserva histórico).

### Sorteio
- **FR-10** O peso de sorteio é `w(p,t) = 1 / (1 + h(p,t))`.
- **FR-11** A escolha de cada tarefa é uma **roleta ponderada** implementada com **árvore de soma**, com pesos atualizados dinamicamente (quem fica inelegível tem o peso zerado na árvore).
- **FR-12** **P1:** a pessoa sorteada para a tarefa `t` não pode ser a que a exerceu no sorteio anterior de `t`.
- **FR-13** **P2:** a carga por pessoa fica em `[⌊m/n⌋, ⌈m/n⌉]`. Logo, se `m ≤ n`, ninguém tem mais de uma tarefa; só há acúmulo quando `m > n`, e então de forma equilibrada.
- **FR-14** O sorteio cobre **todas as tarefas do time de uma vez** (atômico). Uma tentativa que viole P1/P2 é **descartada por inteiro** (reversão automática) e o sorteio recomeça, até `draw.max.attempts`.
- **FR-15** **Relaxamento:** se P1 for impossível (provado por solver exato), viola-se P1 o **mínimo** de vezes. Ordem de prioridade: **cobertura (toda tarefa tem dono) > P2 > P1**.
- **FR-16** O resultado (atribuições, probabilidades, semente, nº de tentativas, modo, justificativas) e a atualização dos contadores `h` são gravados numa **única transação**.
- **FR-17** **Idempotência:** existe no máximo um sorteio por (time, semana). Reexecução na mesma semana reutiliza o sorteio existente.
- **FR-18** Após gravar o sorteio, `h(p,t)` aumenta em 1 para cada par (pessoa, tarefa) sorteado.

### Mensagem
- **FR-20** Uma mensagem por time, uma vez por semana, enviada ao grupo do time pela WhatsApp Cloud API (`recipient_type: "group"`), listando **todas** as tarefas com a pessoa responsável e a **probabilidade** da escolha.
- **FR-21** A mensagem traz **justificativas** quando ocorrer: **J1** pessoa com mais de uma tarefa (sobreposição por `m > n`); **J2** repetição consecutiva da mesma tarefa (P1 relaxada); **J3** sorteio resolvido por fallback determinístico; **J4** (informativa) pessoa nova com histórico zero.
- **FR-22** Modo de envio configurável: `text` (texto livre), `template` (template aprovado) ou `auto` (tenta texto; se a Meta rejeitar por janela de atendimento, usa o template).
- **FR-23** Falha no envio **não perde** o sorteio: o registro fica `PENDING` e o reenvio não re-sorteia nem altera contadores.
- **FR-24** Times são processados isoladamente: erro em um não impede os demais; ao final a função falha se algum time falhou (para disparar retry e alerta).

### Operação
- **FR-30** Execução semanal por EventBridge Scheduler, com expressão cron e fuso configuráveis.
- **FR-31** A Lambda aceita ações manuais: `weekly` (com `dry_run`), `resend`, `revert`, `sync_roster` — ver [contracts/events.md](contracts/events.md).
- **FR-32** *(Should)* `revert` desfaz o último sorteio de um time: remove o registro e decrementa os contadores na mesma transação, permitindo re-sortear a semana.
- **FR-33** Falha da função após os retries dispara e-mail de alerta.

### Infraestrutura
- **FR-40** Toda a infraestrutura é declarada em **um** template CloudFormation ([infra/template.yaml](../../infra/template.yaml)).
- **FR-41** Um script de deploy lê `config/app.properties`, cria/atualiza a stack, grava segredos no SSM e publica o código da Lambda.
- **FR-42** Um script sincroniza o cadastro local (`data/roster.json`) com o banco na AWS.

## 6. Requisitos não funcionais

| ID | Requisito | Meta verificável |
|---|---|---|
| NFR-01 | Lambda enxuta | Python 3.13, `arm64`, 128 MB, 1 função, **0 dependências de terceiros**, pacote ≤ 100 KB, layout plano em `src/` |
| NFR-02 | Free tier | Somente os serviços da tabela em [plan.md §2](plan.md#2-recursos-aws-e-free-tier). Custo AWS esperado: **US$ 0,00/mês** |
| NFR-03 | Segurança | IAM de privilégio mínimo; token só em SSM SecureString; nenhum segredo em logs/template/ambiente/git |
| NFR-04 | Desempenho | ≤ 5 s de CPU por time com n, m ≤ 50 (fora a latência da Meta); timeout da função 60 s |
| NFR-05 | Observabilidade | Logs JSON nativos da Lambda, retenção 30 dias, sem nomes de pessoas |
| NFR-06 | Confiabilidade | Idempotente; Lambda assíncrona com 2 retries; Scheduler com 3 retries; alerta por e-mail |
| NFR-07 | Testabilidade | Núcleo puro com testes de propriedade (invariantes de [algoritmo.md §11](algoritmo.md#11-invariantes-e-testes-de-propriedade)) |
| NFR-08 | Auditabilidade | Semente e probabilidades de cada sorteio gravadas; sorteio reproduzível dado o mesmo estado e semente |

## 7. Critérios de aceite

Formato Dado/Quando/Então. Cada AC aponta o(s) requisito(s) coberto(s).

**AC-01 — Cobertura sem acúmulo** *(FR-11, FR-13)*
Dado um time com 4 pessoas e 3 tarefas, quando roda o sorteio, então cada tarefa tem exatamente 1 pessoa e nenhuma pessoa tem 2 tarefas.

**AC-02 — Premissa 1** *(FR-12)*
Dado que Carla foi responsável por "Ata" na semana anterior e existem outras pessoas elegíveis, quando roda o sorteio, então Carla não é sorteada para "Ata".

**AC-03 — Premissa 2 com sobreposição** *(FR-13, FR-21)*
Dado um time com 2 pessoas e 3 tarefas, quando roda o sorteio, então as cargas são {2, 1} e a mensagem traz a justificativa J1 para quem tem 2 tarefas.

**AC-04 — Probabilidade pelo inverso da frequência** *(FR-10, FR-11, FR-20)*
Dado o cenário numérico de [algoritmo.md §10](algoritmo.md#10-exemplo-numérico), então a probabilidade de Bruno para "Ata" é **63,2 %** (12/19) e aparece assim na mensagem.

**AC-05 — Pessoa nova** *(FR-03, FR-10)*
Dado que Eva entrou no time hoje, então seus contadores `h` são 0 para todas as tarefas, `w = 1` (o máximo) e a mensagem pode trazer J4.

**AC-06 — Reversão automática** *(FR-14, FR-16)*
Dado um sorteio cuja tentativa termina sem candidato para uma tarefa, então a tentativa inteira é descartada, **nada** é gravado dela, e uma nova tentativa é feita; o registro final guarda o nº de tentativas.

**AC-07 — Relaxamento de P1** *(FR-15, FR-21)*
Dado um time com 1 pessoa e 2 tarefas que ela já exerceu na semana anterior, então ambas lhe são atribuídas, o modo é `relaxed` e a mensagem traz J1 e J2.

**AC-08 — Idempotência** *(FR-17)*
Dado que o sorteio de (plataforma, 2026-W42) já está `SENT`, quando a Lambda roda de novo, então não há novo sorteio, não há novo envio e os contadores não mudam.

**AC-09 — Falha no WhatsApp** *(FR-23)*
Dado que a Meta responde erro, então o sorteio fica gravado como `PENDING`, a função falha (retry/alerta) e `resend` envia sem alterar os contadores.

**AC-10 — Sincronização de cadastro** *(FR-03, FR-04, FR-42)*
Dado um `roster.json` com uma pessoa nova e uma pessoa removida, quando sincroniza, então a nova existe com `h = 0` em cada tarefa e a removida fica inativa com histórico preservado; sincronizar de novo não muda nada.

**AC-11 — Dry run** *(FR-31)*
Dado `dry_run: true`, então nada é gravado nem enviado e a resposta traz a mensagem que seria enviada.

**AC-12 — Segredos** *(NFR-03)*
Dado o deploy concluído, então o valor de `secret.*` não aparece no template, nas variáveis de ambiente da Lambda, nos logs nem no git.

**AC-13 — Free tier** *(NFR-02)*
Dado o template, então todos os tipos de recurso pertencem à lista permitida em [plan.md §2](plan.md#2-recursos-aws-e-free-tier).

**AC-14 — Deploy reprodutível** *(FR-40, FR-41)*
Dado um clone limpo e um `config/app.properties` preenchido, então `scripts/deploy.ps1` cria a stack e publica o código sem passos manuais além da confirmação do e-mail de alerta.

## 8. Casos de borda

| Situação | Comportamento esperado |
|---|---|
| `n = 0` ou `m = 0` | Time ignorado (`SKIPPED`), log de aviso; sem mensagem. |
| `n = 1` | P1 impossível ⇒ relaxamento; carga = `m`. |
| `m = n` | Cada pessoa exatamente 1 tarefa. |
| `m > n` | Carga em `{⌊m/n⌋, ⌈m/n⌉}`; J1 para quem tem mais de uma. |
| Responsável anterior saiu do time (inativo) | Não restringe a tarefa (não há quem repetir). |
| Tarefa nova (sem sorteio anterior) | Sem restrição P1. |
| Semana sem execução (ex.: feriado) | "Anterior" = último sorteio existente do time, não necessariamente a semana ISO anterior. |
| Duas invocações simultâneas | A escrita condicional (`attribute_not_exists`) garante um único vencedor; o outro lê o registro existente. |
| Time sem `whatsapp_group_id` | Sorteio **não** é gravado; `ERROR` com motivo `no_group_id`. |
| Token da Meta inválido/expirado | Sem retry inútil; falha com alerta; sorteio `PENDING`. |
| Mensagem > 4096 caracteres | Dividida em várias mensagens por linhas inteiras; justificativas vão na última. |
| Nome de pessoa/tarefa com caracteres de formatação do WhatsApp (`*_~`` ` ``) | Escapados/neutralizados na renderização. |

## 9. Restrições externas — WhatsApp (Meta)

Levantamento feito em **2026-10-10** na documentação oficial. **Este é o maior risco do projeto**,
porque a Cloud API tradicional não falava com grupos e a Groups API tem condições próprias.

| Fato (segundo a documentação da Meta) | Implicação |
|---|---|
| A **Groups API** da Cloud API está aberta a empresas com **Official Business Account (OBA)**; não vale para número do app WhatsApp Business nem para números em Multi-Solution Conversations. | Precisa de número próprio na Cloud API **e** status OBA. Pode ser inviável para um time pequeno. |
| Máximo de **8 participantes** por grupo (10.000 grupos por número). | Time com mais de 7 pessoas não cabe num único grupo com o bot. O sorteio em si não tem esse limite. |
| Grupos são **só por convite**: a empresa cria o grupo, recebe `invite_link` por webhook e envia o link aos membros; um webhook avisa quando alguém entra e o envio passa a ser possível. | Cadastro inicial do grupo é um passo manual (T-00). O `group id` é opaco (string base64), obtido da Groups API. |
| Envio: `POST /{phone_number_id}/messages` com `"recipient_type": "group"` e `"to": "<group id>"`. Suporta texto, mídia e templates; **não** suporta mensagens interativas. | Mensagem em texto simples (ver [contracts/whatsapp.md](contracts/whatsapp.md)). |
| Cobrança **por mensagem entregue × nº de destinatários**. Mensagens **não-template são gratuitas**; templates utility fora da *janela de atendimento* são cobrados. A janela do grupo abre quando **qualquer membro** escreve no grupo. | Um envio semanal "a frio" provavelmente exigirá **template utility aprovado** (custo Meta, **fora** do free tier AWS). Daí o modo `auto`. |

**Não verificado** (a validar na tarefa T-00, antes de implementar o envio): regra exata da janela de
atendimento para texto livre em grupos; limites de taxa; código de erro retornado quando a janela está
fechada; limite de tamanho das variáveis de template em grupos.

**Fontes:** [Groups API](https://developers.facebook.com/documentation/business-messaging/whatsapp/groups) ·
[Envio em grupos](https://developers.facebook.com/documentation/business-messaging/whatsapp/groups/groups-messaging/) ·
[Preços em grupos](https://developers.facebook.com/documentation/business-messaging/whatsapp/groups/pricing) ·
[Preços da plataforma](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing.md).

## 10. Premissas adotadas e pontos a confirmar

Três pontos do pedido original eram ambíguos. Os dois primeiros foram **confirmados pelo solicitante em 2026-10-10**; o terceiro depende da validação T-00.

1. ✅ **Quem entra no time tem peso de sorteio alto.** O que se guarda é o **contador histórico `h = 0`**
   (nunca fez a tarefa), o que, pelo inverso da frequência, dá o **maior** peso de sorteio (`w = 1`).
   O texto original dizia "peso zero" querendo dizer "histórico zero"; a regra de fundo é
   "quem nunca fez tem peso alto". Probabilidade zero para o novato **não** é o comportamento desejado.
2. ✅ **Justificativas** — o pedido original terminava em *"…sobreposição de pessoas ou…"*.
   Confirmado: **"…ou repetição da mesma tarefa em semanas seguidas"** (P1 relaxada, J2).
3. ⏳ **Entrega no grupo.** Assumido que o time **tem** (ou conseguirá) OBA e que o grupo respeita o limite
   de 8 participantes. Se não for possível, as alternativas são: (a) mensagem individual 1:1 por template
   a cada pessoa; (b) provedor não oficial — **descartado** pelo requisito "API oficial". Decidir após T-00.

Decisões de projeto tomadas (com justificativa nos documentos indicados): DynamoDB em vez de SQLite
([data-model.md](data-model.md)); credenciais em `.properties` local → SSM SecureString ([plan.md §4](plan.md#4-credenciais-e-configuração));
código da Lambda fora do CloudFormation, sem S3 ([plan.md §3](plan.md#3-decisões-de-arquitetura)).
