"""Monta o banco DuckDB a partir dos CSVs da Receita Federal (dados abertos CNPJ).

Uso: python build.py <pasta_dos_dados> [arquivo.duckdb]
"""
import sys
import shutil
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import duckdb

if len(sys.argv) < 2:
    sys.exit(__doc__)
DATA = Path(sys.argv[1])
DB = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).with_name("cnpj.duckdb"))

LAYOUTS = {
    "empresas": ("Empresas*", [
        "cnpj_basico", "razao_social", "natureza_juridica", "qualificacao_responsavel",
        "capital_social", "porte", "ente_federativo"]),
    "estab_raw": ("Estabelecimentos*", [
        "cnpj_basico", "cnpj_ordem", "cnpj_dv", "matriz_filial", "nome_fantasia",
        "situacao", "data_situacao", "motivo_situacao", "cidade_exterior", "pais",
        "data_inicio", "cnae_principal", "cnae_secundaria", "tipo_logradouro", "logradouro",
        "numero", "complemento", "bairro", "cep", "uf", "municipio", "ddd1", "telefone1",
        "ddd2", "telefone2", "ddd_fax", "fax", "email", "situacao_especial",
        "data_situacao_especial"]),
    "socios": ("Socios*", [
        "cnpj_basico", "tipo_socio", "nome_socio", "cpf_cnpj_socio", "qualificacao",
        "data_entrada", "pais", "cpf_representante", "nome_representante",
        "qualificacao_representante", "faixa_etaria"]),
    "simples": ("Simples", [
        "cnpj_basico", "opcao_simples", "data_opcao_simples", "data_exclusao_simples",
        "opcao_mei", "data_opcao_mei", "data_exclusao_mei"]),
}
LOOKUPS = ["Cnaes", "Motivos", "Municipios", "Naturezas", "Paises", "Qualificacoes"]


UTF8 = DB.with_name("_utf8")


def convert(fi, dst):
    """Os arquivos da Receita vem em Windows-1252; o DuckDB le UTF-8 nativamente."""
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_name(dst.name + ".part")
    with open(part, "wb") as fo:
        while chunk := fi.read(64 << 20):
            fo.write(chunk.decode("cp1252", errors="replace").encode("utf-8"))
    part.rename(dst)


def transcode(src):
    """Converte um .zip da Receita (sem extrair) ou um arquivo ja extraido."""
    if src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as zf:
            for member in zf.infolist():
                if not member.is_dir():
                    with zf.open(member) as fi:
                        convert(fi, UTF8 / src.stem / Path(member.filename).name)
        return src.name
    with open(src, "rb") as fi:
        convert(fi, UTF8 / src.parent.name / src.name)
    return f"{src.parent.name}/{src.name}"


def sources(glob):
    """Arquivos de uma tabela: pastas ja extraidas ou, na falta delas, os .zip."""
    found = []
    for z in DATA.glob(glob + ".zip"):
        folder = DATA / z.stem
        if not (folder.is_dir() and any(folder.iterdir())):
            found.append(z)
    for d in DATA.glob(glob):
        if d.is_dir():
            found += [f for f in d.iterdir() if f.is_file()]
    return found


def csv(glob, cols):
    path = (UTF8 / glob / "*").as_posix()
    spec = ", ".join(f"'{c}': 'VARCHAR'" for c in cols)
    return (f"read_csv('{path}', delim=';', quote='\"', escape='\"', header=false, "
            f"columns={{{spec}}}, ignore_errors=true, parallel=true)")


def date(col):
    return f"try_strptime(nullif(nullif({col}, ''), '00000000'), '%Y%m%d')::DATE"


def step(con, msg, sql):
    t = time.time()
    print(f"-> {msg}...", flush=True)
    con.execute(sql)
    print(f"   ok ({time.time() - t:.0f}s)", flush=True)


def main():
    if not DATA.is_dir():
        sys.exit(f"Pasta nao encontrada: {DATA}")
    globs = LOOKUPS + [g for g, _ in LAYOUTS.values()]
    files = [f for g in globs for f in sources(g)]
    missing = [g for g in globs if not sources(g)]
    if missing:
        sys.exit(f"Arquivos nao encontrados em {DATA}: {', '.join(missing)}")

    t = time.time()
    print("-> convertendo arquivos para UTF-8...", flush=True)
    with ProcessPoolExecutor(8) as ex:
        for name in ex.map(transcode, files):
            print(f"   {name}", flush=True)
    print(f"   ok ({time.time() - t:.0f}s)", flush=True)

    tmp = DB.with_suffix(".tmp")
    tmp.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute(f"SET memory_limit='5GB'; SET threads=8; SET temp_directory='{tmp.as_posix()}'; "
                "SET preserve_insertion_order=false")

    for name in LOOKUPS:
        step(con, f"tabela {name.lower()}",
             f"CREATE OR REPLACE TABLE {name.lower()} AS "
             f"SELECT * FROM {csv(name, ['codigo', 'descricao'])}")

    for table, (glob, cols) in LAYOUTS.items():
        step(con, f"importando {table}", f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM {csv(glob, cols)}")

    step(con, "tipando socios", f"""
        CREATE OR REPLACE TABLE socios AS SELECT
            cnpj_basico, tipo_socio, nome_socio, cpf_cnpj_socio, qualificacao,
            {date('data_entrada')} AS data_entrada, pais, cpf_representante,
            nome_representante, qualificacao_representante, faixa_etaria
        FROM socios""")

    step(con, "montando tabela estabelecimentos (estab + empresa + simples)", f"""
        CREATE OR REPLACE TABLE estabelecimentos AS SELECT
            e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj,
            e.cnpj_basico, e.matriz_filial,
            em.razao_social, e.nome_fantasia,
            e.situacao, {date('e.data_situacao')} AS data_situacao, e.motivo_situacao,
            {date('e.data_inicio')} AS data_inicio,
            e.cnae_principal, e.cnae_secundaria,
            em.natureza_juridica, em.porte,
            try_cast(replace(em.capital_social, ',', '.') AS DOUBLE) AS capital_social,
            coalesce(s.opcao_simples = 'S' AND {date('s.data_exclusao_simples')} IS NULL, false) AS simples,
            coalesce(s.opcao_mei = 'S' AND {date('s.data_exclusao_mei')} IS NULL, false) AS mei,
            e.tipo_logradouro, e.logradouro, e.numero, e.complemento, e.bairro, e.cep,
            e.uf, e.municipio,
            nullif(e.ddd1 || e.telefone1, '') AS telefone1,
            nullif(e.ddd2 || e.telefone2, '') AS telefone2,
            lower(nullif(e.email, '')) AS email,
            e.pais, e.cidade_exterior, e.situacao_especial
        FROM estab_raw e
        LEFT JOIN empresas em USING (cnpj_basico)
        LEFT JOIN simples s USING (cnpj_basico)
        ORDER BY e.uf, e.municipio, e.cnae_principal""")

    step(con, "limpando tabela temporaria", "DROP TABLE estab_raw")

    step(con, "lista de municipios por UF", """
        CREATE OR REPLACE TABLE municipios_uf AS
        SELECT DISTINCT e.uf, e.municipio AS codigo, m.descricao AS nome
        FROM estabelecimentos e JOIN municipios m ON m.codigo = e.municipio
        WHERE e.uf IS NOT NULL AND e.uf <> 'EX'""")

    step(con, "compactando", "CHECKPOINT")
    for table in ["empresas", "estabelecimentos", "socios", "simples"]:
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"   {table}: {n:,} linhas")
    con.close()
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(UTF8, ignore_errors=True)
    print(f"Pronto: {DB} ({DB.stat().st_size / 1e9:.1f} GB)")


if __name__ == "__main__":
    main()
