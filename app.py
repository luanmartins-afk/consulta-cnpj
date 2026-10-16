"""Consulta CNPJ: prospeccao, estudo de mercado, consulta de empresas e mapa societario.

Rodar: streamlit run app.py
"""
import io
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

import crm

DB = Path(__file__).with_name("cnpj.duckdb")

SITUACAO = {"01": "Nula", "02": "Ativa", "03": "Suspensa", "04": "Inapta", "08": "Baixada"}
PORTE = {"00": "Não informado", "01": "Microempresa", "03": "Pequeno porte", "05": "Demais"}
TIPO_SOCIO = {"1": "Pessoa jurídica", "2": "Pessoa física", "3": "Estrangeiro"}
FAIXA = {"0": "N/A", "1": "0-12", "2": "13-20", "3": "21-30", "4": "31-40", "5": "41-50",
         "6": "51-60", "7": "61-70", "8": "71-80", "9": "80+"}

st.set_page_config(page_title="Consulta CNPJ", page_icon="🏢", layout="wide")


@st.cache_resource
def connect():
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("SET memory_limit='8GB'")
    return con


def q(sql, params=None):
    return connect().cursor().execute(sql, params or []).df()


@st.cache_data
def ufs():
    return q("SELECT DISTINCT uf FROM municipios_uf ORDER BY uf")["uf"].tolist()


@st.cache_data
def municipios(uf):
    df = q("SELECT codigo, nome FROM municipios_uf WHERE uf = ? ORDER BY nome", [uf])
    return dict(zip(df["codigo"], df["nome"]))


@st.cache_data
def cnaes():
    df = q("SELECT codigo, descricao FROM cnaes ORDER BY codigo")
    return {r.codigo: f"{r.codigo[:4]}-{r.codigo[4]}/{r.codigo[5:]} · {r.descricao}" for r in df.itertuples()}


def fmt_cnpj(c):
    c = str(c)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c


def digits(s):
    return re.sub(r"\D", "", s or "")


# ---------- filtros compartilhados ----------

def location_filters(key, require_uf=True):
    c1, c2, c3, c4 = st.columns([1, 3, 2, 1])
    opts = ufs() if require_uf else ["(todas)"] + ufs()
    uf = c1.selectbox("UF", opts, index=opts.index("MG") if "MG" in opts else 0, key=f"{key}_uf")
    uf = None if uf == "(todas)" else uf
    mun = {}
    if uf:
        mun = municipios(uf)
    cidades = c2.multiselect("Município", list(mun), format_func=mun.get, key=f"{key}_mun",
                             placeholder="Todos os municípios da UF")
    bairro = c3.text_input("Bairro (contém)", key=f"{key}_bairro").strip().upper()
    cep = digits(c4.text_input("CEP (início)", key=f"{key}_cep"))
    return uf, cidades, bairro, cep


def cnae_filter(key):
    c1, c2 = st.columns([4, 1])
    sel = c1.multiselect("Ramo de atividade (CNAE)", list(cnaes()), format_func=cnaes().get,
                         key=f"{key}_cnae", placeholder="Digite para buscar: construção, arquitetura, restaurante...")
    sec = c2.checkbox("Incluir CNAE secundário", key=f"{key}_sec",
                      help="Também traz empresas que exercem esse ramo como atividade secundária.")
    return sel, sec


def build_where(uf, cidades, bairro, cep, cnae_sel, cnae_sec, extra=None):
    where, params = [], []
    if uf:
        where.append("e.uf = ?"); params.append(uf)
    if cidades:
        where.append("list_contains(?::VARCHAR[], e.municipio)"); params.append(cidades)
    if bairro:
        where.append("e.bairro LIKE ?"); params.append(f"%{bairro}%")
    if cep:
        where.append("e.cep LIKE ?"); params.append(f"{cep}%")
    if cnae_sel:
        cond = "list_contains(?::VARCHAR[], e.cnae_principal)"
        params.append(cnae_sel)
        if cnae_sec:
            cond = f"({cond} OR list_has_any(string_split(e.cnae_secundaria, ','), ?::VARCHAR[]))"
            params.append(cnae_sel)
        where.append(cond)
    for cond, *p in extra or []:
        where.append(cond); params.extend(p)
    return " AND ".join(where) or "true", params


RESULT_COLS = """
    e.cnpj, e.razao_social, e.nome_fantasia, e.situacao, e.data_situacao, e.data_inicio, e.porte,
    e.capital_social, e.simples, e.mei, e.matriz_filial,
    e.cnae_principal, c.descricao AS cnae_descricao,
    trim(concat_ws(' ', e.tipo_logradouro, e.logradouro, e.numero, e.complemento)) AS endereco,
    e.bairro, e.cep, m.descricao AS municipio, e.uf, e.telefone1, e.telefone2, e.email
"""


def run_search(where, params, limit, order="e.data_inicio DESC"):
    sql = f"""SELECT {RESULT_COLS} FROM estabelecimentos e
              LEFT JOIN cnaes c ON c.codigo = e.cnae_principal
              LEFT JOIN municipios m ON m.codigo = e.municipio
              WHERE {where} ORDER BY {order} LIMIT {int(limit)}"""
    total = q(f"SELECT count(*) n FROM estabelecimentos e WHERE {where}", params)["n"][0]
    df = q(sql, params)
    return total, pretty(df)


def pretty(df):
    df = df.copy()
    if "cnpj" in df:
        df["cnpj"] = df["cnpj"].map(fmt_cnpj)
    if "situacao" in df:
        df["situacao"] = df["situacao"].map(SITUACAO).fillna(df["situacao"])
    if "porte" in df:
        df["porte"] = df["porte"].map(PORTE).fillna(df["porte"])
    if "matriz_filial" in df:
        df["matriz_filial"] = df["matriz_filial"].map({"1": "Matriz", "2": "Filial"})
    return df


def downloads(df, name):
    c1, c2, _ = st.columns([1, 1, 4])
    c1.download_button("⬇ CSV", df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       f"{name}.csv", "text/csv", key=f"{name}_csv")
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    c2.download_button("⬇ Excel", buf.getvalue(), f"{name}.xlsx", key=f"{name}_xlsx")


def show_results(key, name, origem):
    """Mostra o ultimo resultado da busca (guardado na sessao) com selecao de linhas para enviar ao CRM."""
    res = st.session_state.get(f"{key}_res")
    if res is None:
        return None
    msg, df = res
    st.success(msg)
    if aviso := st.session_state.pop(f"{key}_aviso", None):
        st.toast(aviso, icon="✅")
    no_crm = crm.etapas_por_cnpj()
    view = df.copy()
    view.insert(0, "crm", view["cnpj"].map(lambda c: no_crm.get(digits(c), "")))
    ev = st.dataframe(view, width="stretch", hide_index=True, on_select="rerun", selection_mode="multi-row",
                      key=f"{key}_tbl", column_config={"crm": st.column_config.TextColumn("CRM", width="small")})
    rows = ev.selection.rows
    c1, c2 = st.columns([1, 2])
    rotulo = f"➕ Adicionar {len(rows)} selecionada(s) ao CRM" if rows else f"➕ Adicionar todas ({len(df)}) ao CRM"
    if c1.button(rotulo, key=f"{key}_crm"):
        lote = df.iloc[rows] if rows else df
        n = crm.adicionar_empresas(lote, origem)
        st.session_state[f"{key}_aviso"] = (f"{n} lead(s) novo(s) no CRM"
                                            + (f" · {len(lote) - n} já estavam lá" if len(lote) > n else ""))
        st.session_state.crm_v = st.session_state.get("crm_v", 0) + 1
        st.rerun()
    c2.caption("Clique na caixa à esquerda das linhas para selecionar. Sem seleção, envia todas.")
    downloads(df, name)
    return df


def common_extra_filters(key):
    c1, c2, c3, c4 = st.columns(4)
    porte = c1.multiselect("Porte", list(PORTE), format_func=PORTE.get, key=f"{key}_porte",
                           placeholder="Todos")
    situacao = c1.multiselect("Situação cadastral", list(SITUACAO), default=["02"], format_func=SITUACAO.get,
                              key=f"{key}_sit", placeholder="Todas")
    regime = c2.selectbox("Regime", ["Todos", "Excluir MEI", "Só MEI", "Só Simples (sem MEI)"],
                          key=f"{key}_regime")
    contato = c3.multiselect("Exigir contato", ["Telefone", "E-mail"], key=f"{key}_contato")
    matriz = c4.checkbox("Só matriz", key=f"{key}_matriz")
    capital = c4.number_input("Capital social mínimo (R$)", min_value=0, step=10000, key=f"{key}_cap")
    extra = []
    if situacao:
        extra.append(("list_contains(?::VARCHAR[], e.situacao)", situacao))
    if porte:
        extra.append(("list_contains(?::VARCHAR[], e.porte)", porte))
    if regime == "Excluir MEI":
        extra.append(("NOT e.mei",))
    elif regime == "Só MEI":
        extra.append(("e.mei",))
    elif regime == "Só Simples (sem MEI)":
        extra.append(("e.simples AND NOT e.mei",))
    if "Telefone" in contato:
        extra.append(("e.telefone1 IS NOT NULL",))
    if "E-mail" in contato:
        extra.append(("e.email IS NOT NULL",))
    if matriz:
        extra.append(("e.matriz_filial = '1'",))
    if capital:
        extra.append(("e.capital_social >= ?", capital))
    return extra


# ---------- abas ----------

def tab_prospeccao():
    st.caption("Empresas filtradas por situação, região, ramo, porte e data de abertura, com telefone e e-mail.")
    prospeccao("p", "prospeccao", "Prospecção")


def prospeccao(key, name, origem):
    loc = location_filters(key)
    cnae_sel, sec = cnae_filter(key)
    extra = common_extra_filters(key)
    c1, c2, c3 = st.columns([1, 1, 1])
    ini = c1.date_input("Aberta a partir de", value=None, format="DD/MM/YYYY", key=f"{key}_ini")
    fim = c2.date_input("Aberta até", value=None, format="DD/MM/YYYY", key=f"{key}_fim")
    limit = c3.number_input("Máx. de linhas", 100, 200_000, 5_000, step=1000, key=f"{key}_lim")
    if ini:
        extra.append(("e.data_inicio >= ?", ini))
    if fim:
        extra.append(("e.data_inicio <= ?", fim))
    if st.button("Buscar", type="primary", key=f"{key}_go"):
        where, params = build_where(*loc, cnae_sel, sec, extra)
        with st.spinner("Consultando..."):
            total, df = run_search(where, params, limit)
        st.session_state[f"{key}_res"] = (f"{total:,} empresas encontradas".replace(",", ".")
                                          + (f" — mostrando as {len(df):,} mais recentes".replace(",", ".")
                                             if total > len(df) else ""), df)
    show_results(key, name, origem)


def tab_novos():
    st.caption("Empresas **recém-abertas** — costumam precisar de projeto, reforma, mobiliário e serviços.")
    loc = location_filters("n")
    cnae_sel, sec = cnae_filter("n")
    extra = common_extra_filters("n")
    c1, c2 = st.columns(2)
    dias = c1.select_slider("Abertas nos últimos", [7, 15, 30, 60, 90, 180, 365], value=30,
                            format_func=lambda d: f"{d} dias", key="n_dias")
    limit = c2.number_input("Máx. de linhas", 100, 200_000, 5_000, step=1000, key="n_lim")
    ref = q("SELECT max(data_inicio) d FROM estabelecimentos WHERE data_inicio <= current_date")["d"][0]
    st.caption(f"Data mais recente na base: **{ref:%d/%m/%Y}** — o período é contado a partir dela.")
    extra.append(("e.data_inicio >= ?", ref - timedelta(days=dias)))
    if st.button("Buscar", type="primary", key="n_go"):
        where, params = build_where(*loc, cnae_sel, sec, extra)
        with st.spinner("Consultando..."):
            total, df = run_search(where, params, limit)
        st.session_state.n_res = (f"{total:,} empresas abertas no período".replace(",", "."), df)
    res = st.session_state.get("n_res")
    if res is not None and not res[1].empty:
        st.bar_chart(res[1].groupby("cnae_descricao").size().sort_values(ascending=False).head(15),
                     horizontal=True)
    show_results("n", "novos_negocios", "Novos negócios")


def tab_mercado():
    st.caption("Concorrência e densidade de negócios por região, e evolução de aberturas e fechamentos.")
    loc = location_filters("m")
    cnae_sel, sec = cnae_filter("m")
    agrup = st.radio("Agrupar densidade por", ["Bairro", "Município", "CEP (5 dígitos)", "Ramo (CNAE)"],
                     horizontal=True, key="m_agr")
    if not st.button("Analisar", type="primary", key="m_go"):
        return
    where, params = build_where(*loc, cnae_sel, sec)
    with st.spinner("Analisando..."):
        resumo = q(f"""SELECT count(*) FILTER (situacao = '02') ativas,
                              count(*) FILTER (situacao = '08') baixadas,
                              count(*) FILTER (situacao = '02' AND data_inicio >= current_date - INTERVAL 365 DAY) novas_12m,
                              count(*) FILTER (situacao = '08' AND data_situacao >= current_date - INTERVAL 365 DAY) baixadas_12m,
                              count(*) FILTER (situacao = '02' AND mei) mei,
                              median(date_diff('year', data_inicio, current_date)) FILTER (situacao = '02') idade_mediana
                       FROM estabelecimentos e WHERE {where}""", params).iloc[0]
        col = {"Bairro": "e.bairro", "Município": "m.descricao", "CEP (5 dígitos)": "left(e.cep, 5)",
               "Ramo (CNAE)": "c.descricao"}[agrup]
        dens = q(f"""SELECT {col} AS grupo, count(*) AS ativas,
                            count(*) FILTER (e.data_inicio >= current_date - INTERVAL 365 DAY) AS novas_12m
                     FROM estabelecimentos e
                     LEFT JOIN municipios m ON m.codigo = e.municipio
                     LEFT JOIN cnaes c ON c.codigo = e.cnae_principal
                     WHERE {where} AND e.situacao = '02'
                     GROUP BY 1 ORDER BY 2 DESC LIMIT 50""", params)
        anos = q(f"""WITH a AS (SELECT year(data_inicio) ano, count(*) n FROM estabelecimentos e
                                WHERE {where} AND data_inicio IS NOT NULL GROUP BY 1),
                          f AS (SELECT year(data_situacao) ano, count(*) n FROM estabelecimentos e
                                WHERE {where} AND situacao = '08' AND data_situacao IS NOT NULL GROUP BY 1)
                     SELECT coalesce(a.ano, f.ano) AS ano, coalesce(a.n, 0) AS aberturas, coalesce(f.n, 0) AS fechamentos
                     FROM a FULL JOIN f USING (ano) WHERE coalesce(a.ano, f.ano) >= 2000 ORDER BY 1""",
                 params + params)
    k = st.columns(6)
    br = lambda v: f"{int(v):,}".replace(",", ".")
    k[0].metric("Ativas", br(resumo.ativas))
    k[1].metric("Baixadas (total)", br(resumo.baixadas))
    k[2].metric("Abertas 12 meses", br(resumo.novas_12m))
    k[3].metric("Baixadas 12 meses", br(resumo.baixadas_12m))
    k[4].metric("MEI entre ativas", f"{resumo.mei / resumo.ativas:.0%}" if resumo.ativas else "-")
    k[5].metric("Idade mediana", f"{resumo.idade_mediana:.0f} anos" if pd.notna(resumo.idade_mediana) else "-")
    c1, c2 = st.columns(2)
    c1.subheader(f"Densidade por {agrup.lower()} (top 50)")
    c1.bar_chart(dens.set_index("grupo")["ativas"].head(25), horizontal=True)
    c1.dataframe(dens, width="stretch", hide_index=True)
    c2.subheader("Aberturas x fechamentos por ano")
    c2.line_chart(anos.set_index("ano"))
    c2.dataframe(anos, width="stretch", hide_index=True)


def show_empresa(basico):
    emp = q(f"""SELECT {RESULT_COLS}, e.natureza_juridica, n.descricao AS natureza, e.data_situacao,
                       mo.descricao AS motivo, e.cnae_secundaria
                FROM estabelecimentos e
                LEFT JOIN cnaes c ON c.codigo = e.cnae_principal
                LEFT JOIN municipios m ON m.codigo = e.municipio
                LEFT JOIN naturezas n ON n.codigo = e.natureza_juridica
                LEFT JOIN motivos mo ON mo.codigo = e.motivo_situacao
                WHERE e.cnpj_basico = ? ORDER BY e.matriz_filial, e.cnpj""", [basico])
    if emp.empty:
        st.warning("CNPJ não encontrado na base.")
        return
    r = pretty(emp).iloc[0]
    st.subheader(r.razao_social)
    if r.nome_fantasia:
        st.caption(r.nome_fantasia)
    etapa = crm.etapas_por_cnpj().get(emp.cnpj[0])
    if etapa:
        st.info(f"Já está no CRM — etapa **{etapa}**.")
    elif st.button("➕ Adicionar ao CRM", key=f"c_crm_{basico}"):
        crm.adicionar_empresas(emp.head(1), "Consulta de empresa")
        st.rerun()
    k = st.columns(5)
    k[0].metric("Situação (matriz)", r.situacao)
    k[1].metric("Abertura", f"{r.data_inicio:%d/%m/%Y}" if pd.notna(r.data_inicio) else "-")
    k[2].metric("Capital social", f"R$ {r.capital_social:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    k[3].metric("Porte", r.porte)
    k[4].metric("Regime", "MEI" if r.mei else "Simples" if r.simples else "Normal")
    st.write(f"**Natureza jurídica:** {r.natureza} · **CNAE:** {r.cnae_principal} {r.cnae_descricao}")
    if r.situacao != "Ativa":
        st.write(f"**Situação desde:** {r.data_situacao:%d/%m/%Y} — {r.motivo}" if pd.notna(r.data_situacao) else "")
    if r.cnae_secundaria:
        sec = [f"{c} {cnaes().get(c, '').split(' · ')[-1]}" for c in r.cnae_secundaria.split(",")]
        with st.expander(f"CNAEs secundários ({len(sec)})"):
            st.write("\n".join(f"- {s}" for s in sec))
    st.markdown(f"**Estabelecimentos ({len(emp)})**")
    st.dataframe(pretty(emp)[["cnpj", "matriz_filial", "situacao", "nome_fantasia", "endereco", "bairro",
                              "municipio", "uf", "cep", "telefone1", "telefone2", "email"]],
                 width="stretch", hide_index=True)
    soc = socios_de(basico)
    st.markdown(f"**Quadro societário ({len(soc)})**")
    st.dataframe(soc, width="stretch", hide_index=True)


def socios_de(basico):
    df = q("""SELECT s.nome_socio, s.cpf_cnpj_socio, s.tipo_socio, qs.descricao AS qualificacao,
                     s.data_entrada, s.faixa_etaria, s.nome_representante
              FROM socios s LEFT JOIN qualificacoes qs ON qs.codigo = s.qualificacao
              WHERE s.cnpj_basico = ? ORDER BY s.data_entrada""", [basico])
    df["tipo_socio"] = df["tipo_socio"].map(TIPO_SOCIO)
    df["faixa_etaria"] = df["faixa_etaria"].map(FAIXA)
    return df


def tab_consulta():
    st.caption("Digite um CNPJ (completo ou só os 8 primeiros dígitos) ou parte da razão social / nome fantasia.")
    c1, c2 = st.columns([3, 1])
    termo = c1.text_input("CNPJ ou nome", key="c_termo").strip()
    uf = c2.selectbox("UF (para busca por nome)", ["(todas)"] + ufs(), key="c_uf")
    if not termo:
        return
    d = digits(termo)
    if len(d) in (8, 14) and len(d) >= len(termo.replace(".", "").replace("/", "").replace("-", "").replace(" ", "")):
        show_empresa(d[:8])
        return
    params = [f"%{termo.upper()}%", f"%{termo.upper()}%"]
    cond = "e.matriz_filial = '1' AND (e.razao_social LIKE ? OR e.nome_fantasia LIKE ?)"
    if uf != "(todas)":
        cond += " AND e.uf = ?"; params.append(uf)
    with st.spinner("Buscando..."):
        df = q(f"""SELECT e.cnpj_basico, e.cnpj, e.razao_social, e.nome_fantasia, e.situacao,
                          m.descricao AS municipio, e.uf
                   FROM estabelecimentos e LEFT JOIN municipios m ON m.codigo = e.municipio
                   WHERE {cond} ORDER BY e.situacao, e.razao_social LIMIT 200""", params)
    if df.empty:
        st.warning("Nada encontrado.")
        return
    df = pretty(df)
    escolha = st.selectbox(f"{len(df)} resultado(s) — escolha uma empresa", df.index,
                           format_func=lambda i: f"{df.cnpj[i]} · {df.razao_social[i]} · {df.situacao[i]} · {df.municipio[i]}/{df.uf[i]}")
    show_empresa(df.cnpj_basico[escolha])


def tab_socios():
    st.caption("Busque uma pessoa (ou empresa sócia) e veja todas as empresas em que ela aparece no quadro societário. "
               "O CPF vem mascarado pela Receita (***123456**): informe os 6 dígitos do meio para separar homônimos.")
    c1, c2 = st.columns([3, 1])
    nome = c1.text_input("Nome do sócio", key="s_nome").strip().upper()
    cpf = digits(c2.text_input("CPF/CNPJ do sócio (opcional)", key="s_cpf"))
    if len(nome) < 5 and not cpf:
        st.info("Digite pelo menos 5 letras do nome.")
        return
    where, params = [], []
    if nome:
        where.append("s.nome_socio LIKE ?"); params.append(f"%{nome}%")
    if cpf:
        mid = cpf[3:9] if len(cpf) == 11 else cpf
        where.append("s.cpf_cnpj_socio LIKE ?"); params.append(f"%{mid}%")
    with st.spinner("Buscando..."):
        df = q(f"""SELECT s.nome_socio, s.cpf_cnpj_socio, qs.descricao AS qualificacao, s.data_entrada,
                          e.cnpj_basico, e.cnpj, e.razao_social, e.situacao, e.cnae_principal,
                          c.descricao AS cnae_descricao, m.descricao AS municipio, e.uf, e.capital_social
                   FROM socios s
                   JOIN estabelecimentos e ON e.cnpj_basico = s.cnpj_basico AND e.matriz_filial = '1'
                   LEFT JOIN qualificacoes qs ON qs.codigo = s.qualificacao
                   LEFT JOIN cnaes c ON c.codigo = e.cnae_principal
                   LEFT JOIN municipios m ON m.codigo = e.municipio
                   WHERE {' AND '.join(where)}
                   ORDER BY s.nome_socio, s.cpf_cnpj_socio, e.situacao LIMIT 2000""", params)
    if df.empty:
        st.warning("Nenhum sócio encontrado.")
        return
    pessoas = df.groupby(["nome_socio", "cpf_cnpj_socio"]).size().reset_index(name="empresas")
    st.success(f"{len(pessoas)} pessoa(s) / {len(df)} participação(ões) encontradas")
    st.markdown("**Pessoas encontradas**")
    st.dataframe(pessoas, width="stretch", hide_index=True)
    st.markdown("**Empresas em que participam**")
    out = pretty(df.drop(columns="cnpj_basico"))
    st.dataframe(out, width="stretch", hide_index=True)
    downloads(out, "mapa_societario")

    st.markdown("---\n**Rede:** escolha uma das empresas para ver os demais sócios dela")
    escolha = st.selectbox("Empresa", df.index, key="s_emp",
                           format_func=lambda i: f"{fmt_cnpj(df.cnpj[i])} · {df.razao_social[i]}")
    st.dataframe(socios_de(df.cnpj_basico[escolha]), width="stretch", hide_index=True)


# ---------- CRM ----------

def brl(v):
    v = 0 if v is None or pd.isna(v) else v
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def txt(v):
    return "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)


def crm_salvo(msg):
    """Depois de gravar: avisa, limpa as selecoes das tabelas (os indices mudam) e recarrega."""
    st.session_state.crm_aviso = msg
    st.session_state.crm_v = st.session_state.get("crm_v", 0) + 1
    st.rerun()


def situacao(r, hoje, dias):
    """O que fazer com o lead agora, e a prioridade (menor = mais urgente)."""
    if r.etapa == crm.PERDIDO:
        return "", 9
    if r.responder:
        return "⬅ Respondeu — responder", 0
    if pd.notna(r.proximo_contato):
        d = (r.proximo_contato - hoje).days
        if d < 0:
            return f"🔴 Follow-up atrasado {-d} dia(s)", 1
        if d == 0:
            return "🟡 Follow-up hoje", 2
    if r.etapa == "Contatado" and pd.notna(r.ultimo_contato):
        espera = (hoje - r.ultimo_contato.normalize()).days
        if espera >= dias:
            return f"⏳ Sem retorno há {espera} dias — cobrar", 3
        return f"Aguardando retorno ({espera} dia(s))", 5
    if pd.notna(r.proximo_contato):
        return f"📅 {r.proximo_contato:%d/%m/%Y}", 4
    return "", 6


def tab_crm():
    df = crm.leads()
    if aviso := st.session_state.pop("crm_aviso", None):
        st.toast(aviso, icon="✅")
    hoje = pd.Timestamp(date.today())
    dias = st.session_state.get("crm_dias", 3)
    sit = [situacao(r, hoje, dias) for r in df.itertuples()]
    df["situacao"] = [s for s, _ in sit]
    df["prioridade"] = [p for _, p in sit]

    k = st.columns(len(crm.FUNIL) + 1)
    for i, (passo, etapas) in enumerate(crm.FUNIL.items()):
        g = df[df.etapa.isin(etapas)]
        k[i].metric(f"{i + 1}. {passo}", len(g), help=crm.DESCRICAO_FUNIL[passo])
    ganhos, perdidos = df.etapa.isin(crm.GANHAS).sum(), (df.etapa == crm.PERDIDO).sum()
    k[-1].metric("Conversão", f"{ganhos / (ganhos + perdidos):.0%}" if ganhos + perdidos else "-",
                 help=f"Clientes ÷ (clientes + perdidos). Perdidos: {perdidos}")
    a = st.columns(len(crm.FUNIL) + 1)
    a[0].metric("⬅ Retornos para responder", int(df.responder.sum()))
    a[1].metric("🔴 Follow-ups hoje/atrasados", int(df.prioridade.isin([1, 2]).sum()))
    a[2].metric(f"⏳ Sem retorno há {dias}+ dias", int((df.prioridade == 3).sum()))
    a[3].metric("Em proposta", brl(df[df.etapa.isin(crm.FUNIL["Proposta"])].valor.sum()))
    a[4].metric("Clientes (valor)", brl(df[df.etapa.isin(crm.GANHAS)].valor.sum()))

    nomes = [f"{i + 1}. {p}" for i, p in enumerate(crm.FUNIL)]
    sub = st.tabs(nomes + ["📇 Todos"])
    for aba, passo in zip(sub, crm.FUNIL):
        with aba:
            crm_passo(df, passo)
    with sub[-1]:
        crm_passo(df, None)


def crm_passo(df, passo):
    key = f"crm_{passo or 'todos'}"
    etapas = crm.FUNIL[passo] if passo else crm.ETAPAS
    st.caption(crm.DESCRICAO_FUNIL[passo] if passo else "Todos os leads do CRM, inclusive os perdidos.")
    f = df[df.etapa.isin(etapas)]
    if passo == "Filtrar":
        with st.expander("🔍 Filtrar empresas na base e trazer para o CRM", expanded=f.empty):
            st.caption("Os contatos (telefone, e-mail) já vêm da base da Receita. Selecione as empresas e clique em "
                       "**Adicionar ao CRM**. Depois de falar com elas, registre o contato: elas passam para 2. Contato.")
            prospeccao("f", "crm_filtro", "CRM · Filtrar")
    elif passo == "Contato":
        st.number_input("Cobrar retorno depois de quantos dias sem resposta?", 1, 60, 3, key="crm_dias",
                        width=320)
    if f.empty:
        st.info("Nenhum lead neste passo.")
        return
    c1, c2, c3 = st.columns([3, 3, 1])
    busca = c1.text_input("Buscar", key=f"{key}_busca", placeholder="Nome, CNPJ, contato, cidade, e-mail").strip()
    sel = c2.multiselect("Etapa", etapas, key=f"{key}_etapas", placeholder="Todas")
    so_pendentes = c3.checkbox("Só pendências", key=f"{key}_pend",
                               help="Retornos para responder, follow-ups vencidos e contatos sem retorno")
    if busca:
        texto = f[["razao_social", "nome_fantasia", "contato", "municipio", "email", "telefone", "ramo"]] \
            .fillna("").agg(" ".join, axis=1).str.lower()
        mask = texto.str.contains(busca.lower(), regex=False)
        if digits(busca):
            mask |= f.cnpj.fillna("").str.contains(digits(busca), regex=False)
        f = f[mask]
    if sel:
        f = f[f.etapa.isin(sel)]
    if so_pendentes:
        f = f[f.prioridade <= 3]
    f = f.sort_values(["prioridade", "proximo_contato", "atualizado_em"], ascending=[True, True, False])
    st.caption(f"{len(f)} lead(s)")
    lead_table(f.reset_index(drop=True), key)


LEAD_COLS = {"situacao": "O que fazer", "nome": "Empresa", "etapa": "Etapa", "valor": "Valor",
             "contato": "Contato", "telefone": "Telefone", "email": "E-mail", "municipio": "Município",
             "uf": "UF", "ramo": "Ramo", "proximo_contato": "Próximo contato", "ultimo_contato": "Último contato",
             "ultimo_retorno": "Último retorno", "responsavel": "Responsável", "cnpj": "CNPJ", "origem": "Origem"}


def lead_table(df, key):
    view = df.assign(nome=[txt(n) or r for n, r in zip(df.nome_fantasia, df.razao_social)],
                     cnpj=df.cnpj.map(lambda c: fmt_cnpj(c) if txt(c) else ""))[list(LEAD_COLS)]
    data = {"format": "DD/MM/YYYY"}
    ev = st.dataframe(view, width="stretch", hide_index=True, on_select="rerun", selection_mode="multi-row",
                      key=f"{key}_tbl_{st.session_state.get('crm_v', 0)}",
                      column_config={**LEAD_COLS,
                                     "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                                     "proximo_contato": st.column_config.DateColumn("Próximo contato", **data),
                                     "ultimo_contato": st.column_config.DatetimeColumn("Último contato", **data),
                                     "ultimo_retorno": st.column_config.DatetimeColumn("Último retorno", **data)})
    rows = ev.selection.rows
    if len(rows) == 1:
        lead_detail(df.iloc[rows[0]], key)
    elif rows:
        acoes_em_massa(df.iloc[rows], key)
    else:
        st.caption("Selecione um lead para ver o histórico e registrar contatos, ou vários para agir em lote.")
    downloads(view.rename(columns=LEAD_COLS), key)


def acoes_em_massa(sel, key):
    st.divider()
    st.subheader(f"{len(sel)} leads selecionados")
    c1, c2 = st.columns(2, gap="large")
    with c1.form(f"{key}_lote_ativ"):
        st.markdown("**Registrar atividade para todos**")
        a, b = st.columns(2)
        tipo = a.selectbox("Tipo", crm.TIPOS_ATIVIDADE, key=f"{key}_lt")
        quando = b.date_input("Data", date.today(), format="DD/MM/YYYY", key=f"{key}_lq")
        desc = st.text_input("Descrição", key=f"{key}_ld", placeholder="Ex.: mensagem de apresentação no WhatsApp")
        retorno = st.checkbox("⬅ São retornos (eles responderam)", key=f"{key}_lr")
        prox = st.date_input("Agendar próximo contato (opcional)", None, format="DD/MM/YYYY", key=f"{key}_lp")
        if st.form_submit_button("Registrar para todos", type="primary"):
            n = crm.registrar_em_massa(sel.id, tipo, desc or tipo,
                                       datetime.now() if quando == date.today() else quando, retorno)
            if prox:
                for i in sel.id:
                    crm.atualizar_lead(i, {"proximo_contato": prox})
            crm_salvo(f"Atividade registrada em {len(sel)} leads" + (f" · {n} mudaram de etapa" if n else ""))
    with c2.form(f"{key}_lote_mover"):
        st.markdown("**Mover todos para outra etapa**")
        etapa = st.selectbox("Etapa", crm.ETAPAS, key=f"{key}_le")
        motivo = st.text_input("Motivo (se Perdido)", key=f"{key}_lm", placeholder="Sem interesse, fora do perfil...")
        if st.form_submit_button("Mover"):
            for i in sel.id:
                crm.atualizar_lead(i, {"etapa": etapa, "motivo_perda": motivo} if etapa == crm.PERDIDO
                                   else {"etapa": etapa})
            crm_salvo(f"{len(sel)} leads movidos para {etapa}")


def lead_detail(lead, key):
    sfx = f"{key}_{lead.id}"
    st.divider()
    st.subheader(txt(lead.nome_fantasia) or lead.razao_social)
    st.caption(" · ".join(x for x in [lead.razao_social if txt(lead.nome_fantasia) else "",
                                      fmt_cnpj(lead.cnpj) if txt(lead.cnpj) else "", txt(lead.ramo),
                                      f"origem: {lead.origem}" if txt(lead.origem) else "",
                                      f"no CRM desde {lead.criado_em:%d/%m/%Y}"] if x))
    seguinte = crm.ETAPAS[crm.ETAPAS.index(lead.etapa) + 1] if lead.etapa in crm.ETAPAS[:-2] else None
    b1, b2, _ = st.columns([2, 2, 3])
    b1.markdown(f"Etapa: **{lead.etapa}** ({lead.funil})")
    if seguinte and b2.button(f"Avançar para {seguinte} →", key=f"av_{sfx}", type="primary"):
        crm.atualizar_lead(lead.id, {"etapa": seguinte})
        crm_salvo(f"Movido para {seguinte}")
    c1, c2 = st.columns([3, 2], gap="large")
    with c2:
        with st.form(f"ativ_{sfx}"):
            st.markdown("**Registrar contato / retorno**")
            a, b = st.columns(2)
            tipo = a.selectbox("Tipo", crm.TIPOS_ATIVIDADE, key=f"at_{sfx}")
            quando = b.date_input("Data", date.today(), format="DD/MM/YYYY", key=f"aq_{sfx}")
            retorno = st.checkbox("⬅ Foi o lead que respondeu / nos procurou", key=f"ar_{sfx}")
            desc = st.text_area("O que aconteceu?", height=80, key=f"ad_{sfx}")
            nova = st.date_input("Agendar próximo contato (opcional)", None, format="DD/MM/YYYY", key=f"an_{sfx}")
            if st.form_submit_button("Registrar", type="primary"):
                if not desc.strip():
                    st.warning("Descreva o que aconteceu.")
                else:
                    etapa = crm.registrar_atividade(lead.id, tipo, desc,
                                                    datetime.now() if quando == date.today() else quando, retorno)
                    if nova:
                        crm.atualizar_lead(lead.id, {"proximo_contato": nova})
                    crm_salvo("Atividade registrada" + (f" · lead movido para {etapa}" if etapa else ""))
        st.markdown("**Histórico**")
        st.dataframe(crm.atividades(lead.id), width="stretch", hide_index=True,
                     column_config={"data": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY HH:mm"),
                                    "tipo": "Tipo", "sentido": "",
                                    "descricao": st.column_config.TextColumn("Descrição", width="large")})
    with c1.form(f"form_{sfx}"):
        st.markdown("**Dados do lead**")
        a, b = st.columns(2)
        etapa = a.selectbox("Etapa", crm.ETAPAS, index=crm.ETAPAS.index(lead.etapa), key=f"et_{sfx}")
        valor = b.number_input("Valor estimado (R$)", min_value=0.0, step=500.0, key=f"vl_{sfx}",
                               value=float(lead.valor) if pd.notna(lead.valor) else 0.0)
        contato = a.text_input("Pessoa de contato", txt(lead.contato), key=f"ct_{sfx}")
        resp = b.text_input("Responsável", txt(lead.responsavel), key=f"rp_{sfx}")
        tel = a.text_input("Telefone", txt(lead.telefone), key=f"tl_{sfx}")
        email = b.text_input("E-mail", txt(lead.email), key=f"em_{sfx}")
        prox = a.date_input("Próximo contato", lead.proximo_contato.date() if pd.notna(lead.proximo_contato) else None,
                            format="DD/MM/YYYY", key=f"px_{sfx}")
        motivo = b.text_input("Motivo da perda (se Perdido)", txt(lead.motivo_perda), key=f"mp_{sfx}")
        obs = st.text_area("Observações", txt(lead.observacoes), key=f"ob_{sfx}")
        if st.form_submit_button("💾 Salvar"):
            crm.atualizar_lead(lead.id, dict(etapa=etapa, valor=valor or None, contato=contato, responsavel=resp,
                                             telefone=tel, email=email, proximo_contato=prox,
                                             motivo_perda=motivo, observacoes=obs))
            crm_salvo("Lead atualizado")
    with c1.expander("Excluir lead"):
        if st.checkbox("Confirmo que quero excluir este lead e todo o histórico", key=f"dc_{sfx}") \
                and st.button("Excluir", key=f"db_{sfx}"):
            crm.excluir_lead(lead.id)
            crm_salvo("Lead excluído")


# ---------- layout ----------

st.title("🏢 Consulta CNPJ")
if not DB.exists():
    st.error(f"Banco não encontrado em {DB}. Rode primeiro: python build.py <pasta_dos_dados>")
    st.stop()

abas = st.tabs(["🎯 Prospecção", "🆕 Novos negócios", "📊 Estudo de mercado", "🔎 Consulta de empresa",
                "🕸 Mapa societário", "💼 CRM"])
with abas[0]:
    tab_prospeccao()
with abas[1]:
    tab_novos()
with abas[2]:
    tab_mercado()
with abas[3]:
    tab_consulta()
with abas[4]:
    tab_socios()
with abas[5]:
    tab_crm()
st.caption("Fonte: Dados Abertos do CNPJ — Receita Federal. Dados pessoais: use conforme a LGPD.")
