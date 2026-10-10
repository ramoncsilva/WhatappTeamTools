# Contrato — envio ao WhatsApp (Meta Cloud API)

Requisitos: FR-20 a FR-23. Restrições e riscos da Meta: [spec.md §9](../spec.md#9-restrições-externas--whatsapp-meta).

> Itens marcados **[validar T-00]** não puderam ser confirmados na documentação e devem ser
> verificados num número real/sandbox **antes** de implementar `whatsapp.py`.

## 1. Requisição — texto livre

```
POST https://graph.facebook.com/{WA_API_VERSION}/{WA_PHONE_NUMBER_ID}/messages
Authorization: Bearer {token lido do SSM}
Content-Type: application/json
```
```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "group",
  "to": "<whatsapp_group_id do time>",
  "type": "text",
  "text": { "preview_url": false, "body": "<mensagem, §3>" }
}
```
Estrutura conforme o exemplo oficial de envio a grupos (versão da API configurável, `whatsapp.api.version`). Resposta de sucesso: HTTP 200 com `messages[0].id` ⇒ gravado em `wa_message_id`.

## 2. Requisição — template (fallback / modo `template`)

Template **utility**, idioma `pt_BR`, nome em `whatsapp.template.name` (sugestão: `sorteio_semanal`), a ser **criado e aprovado** na Meta. Em grupos a Meta recomenda criar templates novos em vez de reaproveitar os 1:1.

Corpo sugerido (uma única variável, para suportar qualquer nº de tarefas):

```
Sorteio semanal do time {{1}} ({{2}}). Responsáveis: {{3}}
```
```json
{
  "messaging_product": "whatsapp", "recipient_type": "group", "to": "<group id>",
  "type": "template",
  "template": {
    "name": "sorteio_semanal", "language": { "code": "pt_BR" },
    "components": [ { "type": "body", "parameters": [
      { "type": "text", "text": "Plataforma" },
      { "type": "text", "text": "semana 42/2026" },
      { "type": "text", "text": "Ata da daily: Bruno (63,2%) | Café: Carla (75,0%) | Limpeza: Ana (66,7%)" }
    ] } ]
  }
}
```
Restrições do formato **compacto** **[validar T-00]**: parâmetros de template normalmente **não aceitam quebra de linha, tabulação nem 4+ espaços seguidos**, então o texto usa ` | ` como separador e as justificativas vêm resumidas (`Obs: Ana acumula 2 tarefas (mais tarefas que pessoas)`); respeitar o limite de tamanho do corpo (≈1024 caracteres no total) truncando as justificativas com `…` e priorizando a lista de responsáveis.

## 3. Mensagem (texto livre)

Formatação do WhatsApp: `*negrito*`, `_itálico_`. Locale pt-BR (vírgula decimal, 1 casa).

```
📋 *Sorteio semanal — Plataforma*
Semana 42/2026 (12/10 a 18/10)

*Ata da daily* → *Bruno* (63,2%)
*Café* → *Carla* (75,0%)
*Limpeza da sala* → *Ana* (66,7%)

_Chance no momento do sorteio = peso da pessoa ÷ soma dos pesos elegíveis. Peso = 1/(1 + vezes que já fez a tarefa): quem fez menos tem mais chance._

⚠️ *Justificativas*
• Ana ficou com 2 tarefas: há mais tarefas (3) do que pessoas (2).
• Bruno repete "Ata da daily" da semana passada: não havia outra pessoa elegível.

🆕 Eva entrou no time esta semana e começa com chance máxima.
```

Regras de renderização:
1. Ordem das linhas = ordem alfabética do `id` da tarefa (estável entre semanas).
2. Bloco `⚠️ Justificativas` só existe se houver J1/J2/J3; bloco `🆕` só se houver J4.
3. Nomes são **sanitizados**: `*`, `_`, `~` e `` ` `` escapados/removidos; quebras de linha viram espaço.
4. Limite do WhatsApp: 4096 caracteres. Se exceder, dividir em mensagens por **linhas inteiras**, mantendo cabeçalho na primeira e justificativas na última.
5. Função pura `renderizar(sorteio, contexto) -> [str]` — testada sem rede (golden files).

## 4. Tratamento de respostas

| Resposta da Meta | Ação |
|---|---|
| 200 + `messages[0].id` | `status = SENT`, grava `wa_message_id`, `sent_at`. |
| 4xx por **janela de atendimento fechada** (código **[validar T-00]**; em 1:1 é o `131047`) e modo `auto` | Repetir **uma vez** com o template (§2). |
| 401 / código `190` (token inválido ou expirado) | Não repetir; `PENDING`, `last_error="auth"`, falhar (alerta). Renovar `secret.whatsapp.access.token` e rodar `deploy.ps1 -SkipInfra -SkipCode`. |
| 429 / limite de taxa | Repetir até 3 vezes com espera exponencial (1 s, 2 s, 4 s); depois `PENDING`. |
| 5xx / timeout (10 s) | Mesma política do 429. |
| Qualquer outro 4xx | Não repetir; `PENDING`, `last_error` com `code` e `message` da Meta (sem o token). |

`send_attempts` é incrementado a cada chamada ao Graph API. O reenvio posterior (`resend` ou nova execução semanal) **reutiliza** o sorteio.

## 5. Configuração relacionada

| Chave `.properties` | Destino | Segredo? |
|---|---|---|
| `whatsapp.api.version` | env `WA_API_VERSION` | não |
| `whatsapp.phone.number.id` | env `WA_PHONE_NUMBER_ID` | não |
| `whatsapp.send.mode` (`auto`\|`text`\|`template`) | env `WA_SEND_MODE` | não |
| `whatsapp.template.name` / `.language` | env `WA_TEMPLATE_NAME` / `WA_TEMPLATE_LANG` | não |
| `secret.whatsapp.access.token` | SSM SecureString `/<stack>/whatsapp/access-token` | **sim** |
| `whatsapp_group_id` (por time) | banco (cadastro) — vem do `roster.json` | não |

Usar um **token de usuário do sistema** (não expira), com permissão `whatsapp_business_messaging`. Tokens temporários de 24 h do painel não servem para produção.
