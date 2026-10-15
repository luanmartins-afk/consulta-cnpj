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

📘 **Passo a passo completo para Windows (sem precisar programar): [INSTALACAO.md](INSTALACAO.md)**

Resumo:

1. Instale o Python 3.12+ e dê dois cliques em `instalar.bat`.
2. Baixe os 37 `.zip` do mês mais recente em
   <https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/> para uma pasta.
3. Dê dois cliques em `montar_banco.bat` e informe essa pasta.
4. Dê dois cliques em `Abrir Consulta CNPJ.bat`.

Requer ~70 GB livres durante a montagem (~25 GB depois) e 8 GB de RAM (16 GB recomendado).

### Linha de comando

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python build.py C:\caminho\dos\zips
```

O `build.py` lê os `.zip` diretamente (ou pastas já extraídas), converte de Windows-1252 para
UTF-8, importa tudo e gera `cnpj.duckdb` (~24 GB). Leva cerca de 40 minutos e usa até 5 GB de RAM.

## Usar

Dê dois cliques em `Abrir Consulta CNPJ.bat`, ou:

```powershell
.venv\Scripts\python -m streamlit run app.py
```

Abre em <http://localhost:8501>.

## Aviso

Os dados são públicos, mas incluem dados pessoais (nomes, e-mails e telefones de MEIs e sócios).
Use-os conforme a LGPD.
