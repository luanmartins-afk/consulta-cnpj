"""CRM de vendas: leads e atividades guardados em crm.db (SQLite).

Fica separado do cnpj.duckdb porque aquele e somente leitura e e recriado a cada atualizacao da Receita.

O CRM segue quatro passos de trabalho, um para cada parte do funil:
  1. Filtrar   (topo)      Lead                                  empresas filtradas na base, sem contato
  2. Contato   (meio)      Contatado -> Retornou -> Qualificado  retornos, fit e orcamento
  3. Proposta  (fundo)     Proposta enviada -> Negociacao        ate assinar o contrato
  4. Retencao  (pos-venda) Cliente ativo -> Fidelizado           recompra e indicacao
  Perdido (de qualquer etapa)
"""
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

DB = Path(__file__).with_name("crm.db")

FUNIL = {
    "Filtrar": ["Lead"],
    "Contato": ["Contatado", "Retornou", "Qualificado"],
    "Proposta": ["Proposta enviada", "Negociação"],
    "Retenção": ["Cliente ativo", "Fidelizado"],
}
DESCRICAO_FUNIL = {
    "Filtrar": "Topo do funil — empresas filtradas na base, ainda sem contato.",
    "Contato": "Meio do funil — contato feito, retornos e qualificação (fit e orçamento).",
    "Proposta": "Fundo do funil — apresentação da proposta, negociação e assinatura do contrato.",
    "Retenção": "Pós-venda — fidelização, recompra e indicação.",
}
PERDIDO = "Perdido"
ETAPAS = [e for etapas in FUNIL.values() for e in etapas] + [PERDIDO]
FUNIL_DA_ETAPA = {e: f for f, etapas in FUNIL.items() for e in etapas} | {PERDIDO: PERDIDO}
ABERTAS = FUNIL["Filtrar"] + FUNIL["Contato"] + FUNIL["Proposta"]   # ainda em venda
GANHAS = FUNIL["Retenção"]                                          # ja assinaram contrato
CONTATOS = ["Ligação", "WhatsApp", "E-mail", "Reunião", "Visita"]
TIPOS_ATIVIDADE = CONTATOS + ["Anotação"]
DIAS_POS_VENDA = 30
CAMPOS = ["cnpj", "razao_social", "nome_fantasia", "contato", "telefone", "email", "municipio", "uf",
          "ramo", "etapa", "valor", "responsavel", "origem", "proximo_contato", "observacoes", "motivo_perda"]

# etapas da primeira versao do CRM
ETAPAS_ANTIGAS = {"Novo": "Lead", "Contato feito": "Contatado", "Ganho": "Cliente ativo"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY,
    cnpj            TEXT UNIQUE,
    razao_social    TEXT NOT NULL,
    nome_fantasia   TEXT,
    contato         TEXT,
    telefone        TEXT,
    email           TEXT,
    municipio       TEXT,
    uf              TEXT,
    ramo            TEXT,
    etapa           TEXT NOT NULL DEFAULT 'Lead',
    valor           REAL,
    responsavel     TEXT,
    origem          TEXT,
    proximo_contato TEXT,
    observacoes     TEXT,
    motivo_perda    TEXT,
    criado_em       TEXT NOT NULL,
    atualizado_em   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS atividades (
    id        INTEGER PRIMARY KEY,
    lead_id   INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    data      TEXT NOT NULL,
    tipo      TEXT NOT NULL,
    descricao TEXT,
    retorno   INTEGER NOT NULL DEFAULT 0  -- 1 = o lead respondeu / nos procurou
);
CREATE INDEX IF NOT EXISTS atividades_lead ON atividades(lead_id);
"""

_migrados = set()


def _con():
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    if DB not in _migrados:
        con.executescript(SCHEMA)
        if "retorno" not in [c[1] for c in con.execute("PRAGMA table_info(atividades)")]:
            con.execute("ALTER TABLE atividades ADD COLUMN retorno INTEGER NOT NULL DEFAULT 0")
        for antiga, nova in ETAPAS_ANTIGAS.items():
            con.execute("UPDATE leads SET etapa = ? WHERE etapa = ?", [nova, antiga])
        con.commit()
        _migrados.add(DB)
    return con


def _agora():
    return datetime.now().isoformat(timespec="seconds")


def _limpa(v):
    """None para vazio/NaN; datas viram ISO; numpy vira tipo Python."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    if hasattr(v, "item"):
        return v.item()
    if isinstance(v, str):
        return v.strip() or None
    return v


def _log(con, lead_id, tipo, descricao, quando=None, retorno=False):
    con.execute("INSERT INTO atividades (lead_id, data, tipo, descricao, retorno) VALUES (?, ?, ?, ?, ?)",
                [lead_id, quando or _agora(), tipo, descricao, int(retorno)])


def _mudou_etapa(con, lead_id, de, para, motivo=None):
    """Registra a mudanca no historico e agenda o acompanhamento de pos-venda ao assinar contrato."""
    _log(con, lead_id, "Etapa", f"{de} → {para}" + (f" — {motivo}" if para == PERDIDO and motivo else ""))
    if para in GANHAS and de not in GANHAS:
        quando = (date.today() + timedelta(days=DIAS_POS_VENDA)).isoformat()
        con.execute("UPDATE leads SET proximo_contato = ? WHERE id = ?", [quando, lead_id])
        _log(con, lead_id, "Sistema", f"Contrato assinado — pós-venda agendado para {DIAS_POS_VENDA} dias")


def adicionar_empresas(df, origem):
    """Adiciona linhas vindas da base da Receita (colunas de RESULT_COLS) no topo do funil.
    Ignora CNPJs ja cadastrados. Retorna quantos leads novos entraram."""
    agora = _agora()
    novos = 0
    with closing(_con()) as con, con:
        for r in df.to_dict("records"):
            cnpj = re.sub(r"\D", "", str(r.get("cnpj") or "")) or None
            cur = con.execute(
                """INSERT OR IGNORE INTO leads (cnpj, razao_social, nome_fantasia, telefone, email, municipio, uf,
                                                ramo, etapa, origem, observacoes, criado_em, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Lead', ?, ?, ?, ?)""",
                [cnpj, _limpa(r.get("razao_social")) or cnpj, _limpa(r.get("nome_fantasia")),
                 _limpa(r.get("telefone1")), _limpa(r.get("email")), _limpa(r.get("municipio")),
                 _limpa(r.get("uf")), _limpa(r.get("cnae_descricao")), origem,
                 f"Telefone 2: {r['telefone2']}" if _limpa(r.get("telefone2")) else None, agora, agora])
            if cur.rowcount:
                novos += 1
                _log(con, cur.lastrowid, "Sistema", f"Lead criado a partir de: {origem}", agora)
    return novos


def novo_lead(campos):
    agora = _agora()
    dados = {k: _limpa(campos.get(k)) for k in CAMPOS}
    dados["etapa"] = dados["etapa"] or "Lead"
    with closing(_con()) as con, con:
        cur = con.execute(f"""INSERT INTO leads ({', '.join(CAMPOS)}, criado_em, atualizado_em)
                              VALUES ({', '.join('?' * len(CAMPOS))}, ?, ?)""",
                          [dados[k] for k in CAMPOS] + [agora, agora])
        _log(con, cur.lastrowid, "Sistema", f"Lead cadastrado manualmente ({dados['origem'] or 'sem origem'})", agora)
        return cur.lastrowid


def atualizar_lead(lead_id, campos):
    """Grava os campos alterados e registra a mudanca de etapa no historico."""
    lead_id = int(lead_id)
    dados = {k: _limpa(v) for k, v in campos.items() if k in CAMPOS}
    if not dados:
        return
    with closing(_con()) as con, con:
        atual = con.execute("SELECT etapa FROM leads WHERE id = ?", [lead_id]).fetchone()
        con.execute(f"UPDATE leads SET {', '.join(f'{k} = ?' for k in dados)}, atualizado_em = ? WHERE id = ?",
                    list(dados.values()) + [_agora(), lead_id])
        if atual and dados.get("etapa") and dados["etapa"] != atual[0]:
            _mudou_etapa(con, lead_id, atual[0], dados["etapa"], dados.get("motivo_perda"))


def mover_leads(ids, etapa):
    for i in ids:
        atualizar_lead(i, {"etapa": etapa})


def registrar_atividade(lead_id, tipo, descricao, quando, retorno=False):
    """Registra a atividade e avanca o lead quando faz sentido:
    primeiro contato feito (Lead -> Contatado) e lead que respondeu antes de retornar (-> Retornou).
    Retorna a nova etapa, ou None se nao mudou."""
    lead_id = int(lead_id)
    with closing(_con()) as con, con:
        _log(con, lead_id, tipo, descricao, _limpa(quando), retorno)
        etapa = con.execute("SELECT etapa FROM leads WHERE id = ?", [lead_id]).fetchone()[0]
        nova = None
        if retorno and etapa in ("Lead", "Contatado"):
            nova = "Retornou"
        elif not retorno and tipo in CONTATOS and etapa == "Lead":
            nova = "Contatado"
        con.execute("UPDATE leads SET etapa = coalesce(?, etapa), atualizado_em = ? WHERE id = ?",
                    [nova, _agora(), lead_id])
        if nova:
            _mudou_etapa(con, lead_id, etapa, nova)
        return nova


def registrar_em_massa(ids, tipo, descricao, quando, retorno=False):
    return sum(bool(registrar_atividade(i, tipo, descricao, quando, retorno)) for i in ids)


def excluir_lead(lead_id):
    with closing(_con()) as con, con:
        con.execute("DELETE FROM leads WHERE id = ?", [int(lead_id)])


def leads():
    """Todos os leads, com as datas do ultimo contato nosso e do ultimo retorno do lead."""
    contatos = ", ".join(f"'{t}'" for t in CONTATOS)
    with closing(_con()) as con:
        df = pd.read_sql(f"""
            SELECT l.*,
                   (SELECT max(a.data) FROM atividades a WHERE a.lead_id = l.id
                       AND a.tipo NOT IN ('Sistema', 'Etapa')) AS ultima_atividade,
                   (SELECT max(a.data) FROM atividades a WHERE a.lead_id = l.id
                       AND a.retorno = 0 AND a.tipo IN ({contatos})) AS ultimo_contato,
                   (SELECT max(a.data) FROM atividades a WHERE a.lead_id = l.id
                       AND a.retorno = 1) AS ultimo_retorno,
                   (SELECT a.retorno FROM atividades a WHERE a.lead_id = l.id
                       AND (a.retorno = 1 OR a.tipo IN ({contatos}))
                       ORDER BY a.data DESC, a.id DESC LIMIT 1) AS ultimo_foi_retorno
            FROM leads l ORDER BY l.atualizado_em DESC""", con)
    for c in ["proximo_contato", "criado_em", "atualizado_em", "ultima_atividade", "ultimo_contato",
              "ultimo_retorno"]:
        df[c] = pd.to_datetime(df[c], format="ISO8601")
    df["funil"] = df["etapa"].map(FUNIL_DA_ETAPA)
    # o lead falou por ultimo e ainda nao respondemos
    df["responder"] = (df.pop("ultimo_foi_retorno") == 1) & (df.etapa != PERDIDO)
    return df


def atividades(lead_id):
    with closing(_con()) as con:
        df = pd.read_sql("""SELECT data, tipo, CASE WHEN retorno = 1 THEN '⬅ retorno' ELSE '' END AS sentido,
                                   descricao
                            FROM atividades WHERE lead_id = ? ORDER BY data DESC, id DESC""",
                         con, params=[int(lead_id)])
    df["data"] = pd.to_datetime(df["data"], format="ISO8601")
    return df


def etapas_por_cnpj():
    """{cnpj: etapa} de quem ja esta no CRM, para marcar nos resultados de busca."""
    with closing(_con()) as con:
        return dict(con.execute("SELECT cnpj, etapa FROM leads WHERE cnpj IS NOT NULL").fetchall())
