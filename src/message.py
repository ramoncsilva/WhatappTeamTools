"""Justificativas e renderizacao da mensagem semanal. Puro, sem I/O."""

import re
from datetime import date

LIMITE_TEXTO = 4096
LIMITE_COMPACTO = 900


def limpar(nome):
    """Neutraliza formatacao do WhatsApp e quebras de linha em nomes."""
    return re.sub(r"\s+", " ", re.sub(r"[*_~`]", "", str(nome))).strip()


def pct(p):
    return f"{p * 100:.1f}".replace(".", ",") + "%"


def rotulo_semana(semana):
    """'2026-W42' -> ('Semana 42/2026', '12/10 a 18/10')."""
    ano, num = semana.split("-W")
    ini = date.fromisocalendar(int(ano), int(num), 1)
    fim = date.fromisocalendar(int(ano), int(num), 7)
    return f"Semana {int(num)}/{ano}", f"{ini:%d/%m} a {fim:%d/%m}"


def justificar(assignments, mode, n, m, prev, novos):
    """assignments: [{task, person, task_name, person_name, ...}];
    prev: {tarefa: pessoa do sorteio anterior}; novos: nomes de quem entrou apos o sorteio anterior.
    Devolve [{code, text}] (J1..J4)."""
    out = []
    cargas = {}
    for a in assignments:
        cargas.setdefault(a["person"], []).append(a)
    for itens in cargas.values():
        if len(itens) > 1:
            nome = limpar(itens[0]["person_name"])
            out.append({"code": "J1", "text":
                        f"{nome} ficou com {len(itens)} tarefas: há mais tarefas ({m}) do que pessoas ({n})."})
    for a in assignments:
        if prev.get(a["task"]) == a["person"]:
            out.append({"code": "J2", "text":
                        f'{limpar(a["person_name"])} repete "{limpar(a["task_name"])}" da semana passada: '
                        "não havia outra pessoa elegível."})
    if mode == "fallback":
        out.append({"code": "J3", "text": "Sorteio resolvido por atribuição determinística após esgotar as tentativas."})
    for nome in novos:
        out.append({"code": "J4", "text":
                    f"{limpar(nome)} entrou no time esta semana e começa com chance máxima."})
    return out


def renderizar(time_nome, semana, assignments, justificativas):
    """Texto livre, dividido em partes de ate 4096 caracteres (por linhas inteiras)."""
    sem, faixa = rotulo_semana(semana)
    linhas = [f"📋 *Sorteio semanal — {limpar(time_nome)}*", f"{sem} ({faixa})", ""]
    for a in assignments:
        linhas.append(f'*{limpar(a["task_name"])}* → *{limpar(a["person_name"])}* ({pct(a["p"])})')
    linhas += ["", "_Chance no momento do sorteio = peso da pessoa ÷ soma dos pesos elegíveis. "
               "Peso = 1/(1 + vezes que já fez a tarefa): quem fez menos tem mais chance._"]
    excecoes = [j for j in justificativas if j["code"] in ("J1", "J2", "J3")]
    novos = [j for j in justificativas if j["code"] == "J4"]
    if excecoes:
        linhas += ["", "⚠️ *Justificativas*"] + [f"• {j['text']}" for j in excecoes]
    if novos:
        linhas += [""] + [f"🆕 {j['text']}" for j in novos]
    return _dividir(linhas)


def _dividir(linhas):
    partes, atual = [], ""
    for linha in linhas:
        candidato = f"{atual}\n{linha}" if atual else linha
        if len(candidato) > LIMITE_TEXTO and atual:
            partes.append(atual)
            candidato = linha
        atual = candidato
    partes.append(atual)
    return partes


def compacto(time_nome, semana, assignments, justificativas):
    """Parametros do template (uma linha so, sem \\n): (time, semana, responsaveis)."""
    sem, _ = rotulo_semana(semana)
    itens = [f'{limpar(a["task_name"])}: {limpar(a["person_name"])} ({pct(a["p"])})' for a in assignments]
    texto = " | ".join(itens)
    obs = [j["text"] for j in justificativas if j["code"] in ("J1", "J2", "J3")]
    if obs:
        texto += " | Obs: " + " ".join(obs)
    if len(texto) > LIMITE_COMPACTO:
        texto = texto[: LIMITE_COMPACTO - 1].rstrip() + "…"
    return [limpar(time_nome), sem.lower(), texto]
