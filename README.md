# WhatappTeamTools

Sorteio semanal de tarefas de times, publicado no grupo de WhatsApp pela API oficial da Meta.

Uma AWS Lambda enxuta sorteia, **de uma vez**, o responsável por cada tarefa de cada time com uma
**roleta inversa de pesos dinâmicos** (árvore de soma): quem fez menos uma tarefa tem mais chance de
pegá-la. Ninguém repete a mesma tarefa em semanas seguidas e ninguém acumula tarefas a não ser que
haja mais tarefas que pessoas. A mensagem semanal mostra a probabilidade de cada escolha e justifica
qualquer exceção. Roda 100 % em serviços *Always Free* da AWS.

> **Estado:** spec, infraestrutura, scripts e o código da Lambda (`src/`, sem dependências) estão prontos e testados
> localmente (`tests/`). **Ainda não foi implantado na AWS** e o envio ao WhatsApp aguarda a validação T-00 em
> [tasks.md](specs/001-sorteio-semanal/tasks.md).

## Leia nesta ordem

| Documento | Conteúdo |
|---|---|
| [specs/constitution.md](specs/constitution.md) | Princípios do projeto |
| [specs/001-sorteio-semanal/spec.md](specs/001-sorteio-semanal/spec.md) | **O quê e por quê**: requisitos, critérios de aceite, riscos da Meta, premissas a confirmar |
| [specs/001-sorteio-semanal/algoritmo.md](specs/001-sorteio-semanal/algoritmo.md) | Algoritmo, árvore de soma, exemplo numérico, invariantes |
| [specs/001-sorteio-semanal/data-model.md](specs/001-sorteio-semanal/data-model.md) | Modelo de dados (DynamoDB) e por que não SQLite |
| [specs/001-sorteio-semanal/plan.md](specs/001-sorteio-semanal/plan.md) | **Como**: arquitetura, free tier, credenciais, módulos, deploy |
| [specs/001-sorteio-semanal/tasks.md](specs/001-sorteio-semanal/tasks.md) | Tarefas ordenadas e rastreabilidade |
| [specs/001-sorteio-semanal/contracts/](specs/001-sorteio-semanal/contracts/) | Eventos da Lambda, arquivo de cadastro, payloads do WhatsApp |

## Sincronizando com a AWS

Pré-requisitos: [AWS CLI v2](https://aws.amazon.com/cli/) com credenciais configuradas (`aws configure sso`) e PowerShell.

```powershell
# 1. Configuração e credenciais (arquivo ignorado pelo git)
Copy-Item config\app.properties.example config\app.properties   # editar: região, e-mail, phone id, token...

# 2. Infraestrutura + segredo no SSM + código da Lambda
.\scripts\deploy.ps1                       # -SkipInfra / -SkipSecrets / -SkipCode para etapas isoladas

# 3. Cadastro de times, pessoas e tarefas
Copy-Item data\roster.example.json data\roster.json             # editar
.\scripts\sync-roster.ps1 -DryRun          # mostra o que mudaria
.\scripts\sync-roster.ps1

# 4. Operação
.\scripts\invoke.ps1 -Action weekly -DryRun                     # sorteia e mostra a mensagem, sem gravar/enviar
.\scripts\invoke.ps1 -Action resend -Team plataforma -Week 2026-W42
.\scripts\invoke.ps1 -Action revert -Team plataforma
```

Testes locais: `pip install -r tests/requirements-dev.txt` e `python -m pytest tests`.

## Estrutura

```
specs/      especificação (fonte da verdade)
infra/      template CloudFormation
config/     app.properties.example  (app.properties real é ignorado)
data/       roster.example.json     (roster.json real é ignorado)
scripts/    deploy / sync-roster / invoke (PowerShell)
src/        Lambda (layout plano, só stdlib + boto3)
tests/      pytest (algoritmo, mensagem, cadastro, DynamoDB simulado, WhatsApp local, template)
```
