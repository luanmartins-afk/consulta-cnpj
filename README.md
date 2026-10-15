# Consulta CNPJ

Ferramenta local para cruzar e filtrar os **Dados Abertos do CNPJ** da Receita Federal
(empresas, estabelecimentos, sócios e Simples/MEI) — prospecção B2B, estudo de mercado,
consulta de empresas e mapa societário.

## Abas

| Aba | O que faz |
|---|---|
| 🎯 Prospecção | Empresas ativas por UF, município, bairro, CEP, CNAE (principal/secundário), porte, regime, capital e data de abertura; exporta Excel/CSV |
| 🆕 Novos negócios | Empresas abertas nos últimos 7–365 dias por região e ramo |
| 📊 Estudo de mercado | Ativas, baixadas, aberturas x fechamentos por ano, densidade por bairro/município/CEP/ramo |
| 🔎 Consulta de empresa | Busca por CNPJ ou nome: situação, capital, porte, regime, CNAEs, filiais e sócios |
| 🕸 Mapa societário | Todas as empresas em que uma pessoa é sócia, e os demais sócios de cada uma |

## Instalação

Requer Python 3.12+ e ~60 GB livres em disco durante a montagem do banco.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Montar o banco

1. Baixe os arquivos `.zip` em <https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/>
   (Empresas, Estabelecimentos, Socios, Simples, Cnaes, Motivos, Municipios, Naturezas, Paises, Qualificacoes).
2. Extraia cada `.zip` numa pasta com o mesmo nome (ex.: `Empresas0.zip` → `Empresas0\`).
3. Rode:

```powershell
.venv\Scripts\python build.py C:\caminho\da\pasta\com\os\dados
```

O script converte os arquivos (Windows-1252 → UTF-8), importa tudo e gera `cnpj.duckdb`
(~24 GB). Leva cerca de 40 minutos e usa até 5 GB de RAM.

## Usar

Dê dois cliques em `Abrir Consulta CNPJ.bat`, ou:

```powershell
.venv\Scripts\python -m streamlit run app.py
```

Abre em <http://localhost:8501>.

## Aviso

Os dados são públicos, mas incluem dados pessoais (nomes, e-mails e telefones de MEIs e sócios).
Use-os conforme a LGPD.
