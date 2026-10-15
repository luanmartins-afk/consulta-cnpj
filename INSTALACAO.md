# Como instalar a Consulta CNPJ

Guia passo a passo para Windows. Não precisa saber programar.

São 4 etapas: **baixar o projeto → instalar → baixar os dados da Receita → montar o banco**.
A instalação inteira leva cerca de 1h30, a maior parte esperando downloads e a montagem do banco.
Depois disso, a ferramenta abre em segundos.

---

## Antes de começar: o que você precisa

| Item | Mínimo | Recomendado |
|---|---|---|
| Sistema | Windows 10 ou 11 | Windows 11 |
| Memória RAM | 8 GB | 16 GB |
| Espaço livre em disco | 70 GB durante a montagem (sobram ~25 GB depois) | SSD |
| Internet | para baixar ~7 GB de dados | — |

---

## Etapa 1 — Baixar o projeto

**Opção A (mais simples):**
1. Na página do projeto no GitHub, clique no botão verde **Code** → **Download ZIP**.
2. Extraia o ZIP numa pasta fácil de achar, por exemplo `C:\ConsultaCNPJ`.

> Evite pastas dentro do OneDrive: o banco tem ~24 GB e o OneDrive tentaria sincronizá-lo.

**Opção B (quem usa GitHub Desktop):** **File → Clone repository** e escolha `consulta-cnpj`.

---

## Etapa 2 — Instalar

### 2.1 Instalar o Python (só na primeira vez)

1. Acesse <https://www.python.org/downloads/> e baixe o **Python 3.12** (ou mais novo).
2. Execute o instalador e **marque a caixa "Add python.exe to PATH"** na primeira tela.
3. Clique em **Install Now**.

Já tem Python? Pode pular esta parte.

### 2.2 Instalar a ferramenta

Na pasta do projeto, dê **dois cliques em `instalar.bat`**.

Uma janela preta vai abrir, instalar as bibliotecas e mostrar **"Instalacao concluida!"**.
Leva de 2 a 5 minutos.

> Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.

---

## Etapa 3 — Baixar os dados da Receita Federal

Os dados são públicos e atualizados todo mês pela Receita.

1. Acesse <https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/>
2. Entre na pasta do **mês mais recente** (ex.: `2026-10/`).
3. Crie uma pasta vazia para os dados, por exemplo `C:\DadosCNPJ`, e baixe **todos os .zip** do mês para ela:

| Arquivos | Quantos | Tamanho aprox. |
|---|---|---|
| `Empresas0.zip` … `Empresas9.zip` | 10 | 1 GB |
| `Estabelecimentos0.zip` … `Estabelecimentos9.zip` | 10 | 5 GB |
| `Socios0.zip` … `Socios9.zip` | 10 | 0,7 GB |
| `Simples.zip` | 1 | 0,3 GB |
| `Cnaes.zip`, `Motivos.zip`, `Municipios.zip`, `Naturezas.zip`, `Paises.zip`, `Qualificacoes.zip` | 6 | < 1 MB |

São **37 arquivos**, ~7 GB no total. **Não precisa extrair** — o próximo passo faz isso sozinho.

---

## Etapa 4 — Montar o banco de dados

1. **Feche programas pesados** (Chrome com muitas abas, AutoCAD, Photoshop etc.). A montagem usa bastante memória.
2. Na pasta do projeto, dê **dois cliques em `montar_banco.bat`**.
3. Quando pedir, cole o caminho da pasta dos dados (ex.: `C:\DadosCNPJ`) e tecle **Enter**.
   - Dica: no Explorador de Arquivos, clique na barra de endereço da pasta, copie e cole na janela preta com o botão direito do mouse.
4. Aguarde. Leva **30 a 60 minutos**. Não feche a janela.
   Ao final aparece **"Pronto!"** e a contagem de linhas de cada tabela.

Depois disso, a pasta `C:\DadosCNPJ` pode ser apagada para liberar espaço — tudo fica no arquivo `cnpj.duckdb`.

---

## Usar no dia a dia

Dê **dois cliques em `Abrir Consulta CNPJ.bat`**. O navegador abre sozinho em <http://localhost:8501>.

Para fechar, feche a janela preta que abriu junto.

| Aba | Para quê |
|---|---|
| 🎯 Prospecção | Listar empresas ativas por região, ramo (CNAE), porte e data de abertura, com telefone e e-mail. Exporta para Excel. |
| 🆕 Novos negócios | Empresas recém-abertas — potenciais clientes de projeto, reforma e serviços. |
| 📊 Estudo de mercado | Concorrência e densidade por bairro, aberturas x fechamentos por ano. |
| 🔎 Consulta de empresa | Situação, capital, regime, filiais e sócios de um CNPJ. |
| 🕸 Mapa societário | Todas as empresas em que uma pessoa é sócia. |

---

## Atualizar os dados (mensal)

1. Baixe os .zip do novo mês numa pasta nova (Etapa 3).
2. Rode `montar_banco.bat` de novo apontando para essa pasta. O banco antigo é substituído.

---

## Problemas comuns

| Problema | Solução |
|---|---|
| **"Python não encontrado"** no `instalar.bat` | Reinstale o Python marcando **"Add python.exe to PATH"**. Feche e abra o `.bat` de novo. |
| A montagem **parou no meio** ou o PC travou | Falta de memória. Feche todos os programas e rode `montar_banco.bat` de novo — os arquivos já convertidos são aproveitados. |
| **"Pasta nao encontrada"** | Confira o caminho colado. Não precisa de aspas. |
| **Erro de espaço em disco** | Libere ~70 GB no disco onde está o projeto. |
| O navegador **não abriu** | Abra manualmente <http://localhost:8501> com a janela preta ainda aberta. |
| **"Port 8501 is already in use"** | A ferramenta já está aberta em outra janela. Use essa, ou feche-a e abra de novo. |
| Consultas **lentas** | A primeira consulta após abrir é mais lenta (carrega o banco). Filtrar por UF/município deixa tudo mais rápido. |
| Antivírus bloqueia o `.bat` | Os scripts só instalam bibliotecas Python e rodam a ferramenta localmente. Libere a pasta do projeto no antivírus. |

---

## Privacidade e LGPD

A ferramenta roda **100% no seu computador** — nenhum dado é enviado para a internet.

Os dados da Receita são públicos, mas incluem **dados pessoais** (nomes, telefones e e-mails de MEIs e sócios).
Para contato comercial, respeite a LGPD: tenha uma base legal (ex.: legítimo interesse), identifique-se,
ofereça a opção de não receber mais contatos e não envie spam.
