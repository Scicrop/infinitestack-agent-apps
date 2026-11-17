# Configuração de Agent Apps e pacotes do Skills Lab

Especificação do arquivo de configuração de um Agent App e dos pacotes do Skills Lab ligados a ele:
o formato do documento, como cada app descreve os próprios parâmetros, como apontar para dados
sem escrever credenciais e onde cada arquivo mora.

> **Estado: proposta, versão 1 do envelope (`configVersion: 1`).** A fase 1 (seção 10) não depende
> de mudança no host e pode ser adotada já. A fase 2 depende de issue no `infinitestack-back`.

---

## Índice

1. [Por que existe](#1-por-que-existe)
2. [A ideia em um parágrafo](#2-a-ideia-em-um-parágrafo)
3. [Os arquivos e onde moram](#3-os-arquivos-e-onde-moram)
4. [O documento de configuração](#4-o-documento-de-configuração)
5. [Referências a dados (`data`)](#5-referências-a-dados-data)
6. [Credenciais](#6-credenciais)
7. [O schema do app](#7-o-schema-do-app)
8. [Carga, mescla e validação](#8-carga-mescla-e-validação)
9. [Edição pela tela de Configurações](#9-edição-pela-tela-de-configurações)
10. [Fases: o que o app faz hoje e o que passa ao host](#10-fases-o-que-o-app-faz-hoje-e-o-que-passa-ao-host)
11. [Empacotamento](#11-empacotamento)
12. [Migração de um app existente](#12-migração-de-um-app-existente)
13. [O que não entra neste arquivo](#13-o-que-não-entra-neste-arquivo)
14. [Exemplo completo](#14-exemplo-completo)
15. [Referência: schema do envelope v1](#15-referência-schema-do-envelope-v1)
16. [Decisões em aberto](#16-decisões-em-aberto)

---

## 1. Por que existe

Os primeiros Agent Apps com pacote de Skills Lab acabaram com cada um configurado de um jeito:

- **Três mecanismos ao mesmo tempo:** `application.properties` com `${VAR:default}` no `.ispz`,
  `.env` lido por um `config.py`/`settings.py` no pacote Python e um `.properties` ou `.env` solto
  por instância em `/opt/infinitestack/etc/data/`.
- **Estruturas escritas como texto, cada uma com o próprio parser:** mapa como
  `A:Nome um;B:Nome dois`, lista como `00,06,12,18`, intervalo como `2017-2025`, bbox como
  `-80,-40,10,10`, par como `ecmwf:51`, referência a uma fonte como `mirror:SCHEMA.TABELA`. Um
  pacote de ingestão chegou a ter uns 60 parâmetros nesse formato.
- **Valores repetidos entre o `.ispz` e o pacote:** a pasta de saída, os nomes das tabelas gold e
  o arquivo de credenciais declarados nos dois lados, sem nada que garanta que fiquem iguais.
- **Acesso a dados sem padrão:** tabela gold passada por nome, app lendo o
  `catalogExplorerMirror.json` direto (e vendo as credenciais do `metadata`), credencial Azure
  apontada por "arquivo + prefixo de chave" e às vezes emprestada do arquivo de outro app, e
  caminho do lake escrito por extenso.

Esta especificação troca tudo isso por um documento JSON só, tipado e validado.

---

## 2. A ideia em um parágrafo

Um Agent App e seus pacotes compartilham **um documento de configuração** em JSON. O documento tem
um envelope fixo, igual para todo app, com blocos padronizados para o que é comum (referências a
dados), e seções livres (`shared`, `app`, `skills.<pacote>`) para os parâmetros próprios. O schema
do envelope é desta especificação; o schema das seções livres é do app, escrito em JSON Schema e
levado dentro do pacote. O pacote traz os valores padrão; a instância sobrescreve o que muda nela
num arquivo fora do pacote, que um admin edita pela tela de Configurações do próprio app. Duas
pessoas não sobrescrevem uma à outra: a gravação só passa se o arquivo ainda está na revisão que a
tela leu. **Credencial nunca entra no documento:** os dados são apontados por
referência (tabela, mirror, fonte do catálogo, URI de storage), e quando uma referência precisa de
credencial ela leva só o **nome** de uma credencial guardada à parte.

---

## 3. Os arquivos e onde moram

| Arquivo | Onde | Quem escreve | Vai no repo? |
|---|---|---|---|
| `app-config.schema.json` | no `.ispz` (`config/`) e no pacote do Skills Lab | dev | sim |
| `app-config.json` (padrões) | no `.ispz` (`config/`) e no pacote do Skills Lab | dev | sim |
| `<plugin_id>.config.json` (instância) | `/opt/infinitestack/etc/data/` | o `.ispz`, pela tela de Configurações (seção 9) | **não** |
| `app-credentials.json` (fase 1) | `/opt/infinitestack/etc/data/`, permissão `600` | operador da instância | **nunca** |

- **Padrões vs. instância.** O `app-config.json` do pacote tem tudo que funciona em qualquer
  instalação. O `<plugin_id>.config.json` da instância tem só o que muda nela: o projeto, as
  unidades do cliente, a conta de storage. Ninguém copia o arquivo inteiro.
- **Quem grava a instância é o `.ispz`,** quando um `ADMIN` ou `SCICROP` salva na tela de
  Configurações. Os pacotes do Skills Lab só leem. Editar o arquivo à mão no servidor continua
  possível, por exemplo para recuperar uma instância que não sobe, e a revisão por hash (seção 9)
  percebe a edição.
- **Um documento para o app e os pacotes.** O `.ispz` e os pacotes do Skills Lab do mesmo app leem o
  mesmo arquivo de instância (`<plugin_id>.config.json`), porque rodam no mesmo contêiner do back
  do IS. Cada um lê o que precisa: o `.ispz` lê `data`, `shared` e `app`; um pacote lê `data`,
  `shared` e `skills.<nome-do-pacote>`.
- **Fonte única no repo do app.** Os padrões e o schema ficam numa pasta `config/` na raiz do repo
  do app, e o build copia para o `.ispz` e para cada pacote (seção 11). Ninguém edita a cópia.
- **Dev local.** A variável `APP_CONFIG_FILE` aponta para outro arquivo de instância (ex.:
  `config/local.config.json` no repo, fora do commit se tiver dado de cliente). É o único override
  por ambiente: não há variável de ambiente por chave.

> Variáveis com prefixo `IS_` são do host e ele as sobrescreve. Por isso a variável de dev é
> `APP_CONFIG_FILE`, sem o prefixo.

---

## 4. O documento de configuração

```jsonc
{
  "configVersion": 1,                 // versão do envelope (esta especificação)
  "pluginId": "atmo-agent-app",       // igual ao plugin_id do manifest
  "schemaVersion": 3,                 // versão do schema do app (seção 7)

  "data": {                           // referências a dados, por apelido (seção 5)
    "gfsForecast": { "kind": "table", "table": "gold.br_weather_agent_app_gfs_step" },
    "renders":     { "kind": "storage", "uri": "lake://gold/atmo-agent-app/renders/" }
  },

  "shared": { },                      // parâmetros lidos pelo .ispz e pelos pacotes
  "app":    { },                      // parâmetros só do .ispz
  "skills": {                         // parâmetros só de cada pacote do Skills Lab
    "atmo-render": { }
  }
}
```

| Campo | Obrigatório | O que é |
|---|---|---|
| `configVersion` | sim | versão do envelope. Hoje só `1` |
| `pluginId` | sim | `plugin_id` do app. O carregador recusa um documento de outro app |
| `schemaVersion` | sim nos padrões do pacote | versão do schema do app. Ver seção 7 |
| `data` | não | mapa `apelido → referência`. Formato fixo (seção 5) |
| `shared` | não | objeto livre, validado pelo schema do app |
| `app` | não | objeto livre, validado pelo schema do app |
| `skills` | não | mapa `nome do pacote → objeto livre`, validado pelo schema do app |

Convenções para as seções livres:

- **Chaves em camelCase, em inglês**, como o resto do código.
- **Unidade no nome da chave** quando o valor tem unidade: `httpTimeoutSeconds`,
  `maxStationDistanceKm`, `heavyRainMm`, `cacheMaxGb`.
- **Estrutura de verdade, nunca texto codificado:** lista é array, mapa é objeto, intervalo é
  objeto com `from`/`to`, bbox é objeto com `west`/`south`/`east`/`north`. A seção 7 traz os tipos
  reutilizáveis.
- **Apelidos de `data` em camelCase** e estáveis: o código procura pelo apelido.

---

## 5. Referências a dados (`data`)

Cada entrada de `data` diz **onde está o dado**, nunca **como entrar**. O tipo vem em `kind`:

| `kind` | Aponta para | Credencial |
|---|---|---|
| `table` | tabela no banco de destino do IS (`gold`, `silver`, `bronze`, `apps`) | nenhuma: usa o datasource injetado pelo host |
| `mirror` | tabela no lakehouse externo do `catalogExplorerMirror.json` | a do mirror, resolvida pelo catálogo |
| `catalog` | fonte do `catalogExplorer.json`, pelo nome ou id | a da fonte, resolvida pelo catálogo |
| `storage` | arquivo ou prefixo por URI: lake do IS, Azure, S3, GCS ou `https` | opcional, pelo nome |
| `http` | API externa | opcional, pelo nome |

Todo tipo aceita `description` (texto livre para quem opera).

### 5.1 `table`

```json
{ "kind": "table", "table": "gold.br_geo_agent_app_ibge_municipality" }
```

`table` é sempre `schema.tabela`, como manda a regra de SQL qualificado. É o caso mais comum: um app
lendo a tabela gold que outro app (ou o próprio pacote) materializou.

### 5.2 `mirror`

```json
{ "kind": "mirror", "table": "PRD_GOLD.DAILY_WEATHER" }
```

Tabela do lakehouse externo, consultada ao vivo, em `schema.tabela` ou, onde o lakehouse tem
catálogo (Databricks), `catalogo.schema.tabela`. O `catalogExplorerMirror.json` tem exatamente uma
conexão, então a referência não precisa dizer qual. O campo `source` (nome da conexão) é aceito e
reservado para quando o host permitir mais de uma.

### 5.3 `catalog`

```json
{ "kind": "catalog", "source": "erp-producao", "table": "dbo.talhao" }
```

Uma fonte cadastrada no Catalog Explorer, pelo `name` ou pelo `id` (UUID) do `SourceDTO`. O
`table` é opcional. Use só quando o app precisa da **origem ao vivo**. Se o dado já é ingerido pelo
IS, aponte para a tabela de destino com `kind: "table"`, que não precisa de credencial nenhuma.

### 5.4 `storage`

```json
{ "kind": "storage", "uri": "abfss://dados@contacliente.dfs.core.windows.net/geo/blocks.parquet",
  "credential": "azure-cliente", "format": "parquet" }
```

| Esquema da URI | Onde | Exemplo |
|---|---|---|
| `lake://` | lake do IS, relativo a `/opt/infinitestack/var/lake/` | `lake://bronze/br-weather-agent-app/redemet/` |
| `abfss://` | Azure ADLS Gen2 / Blob | `abfss://<container>@<conta>.dfs.core.windows.net/<caminho>` |
| `s3://` | AWS S3 | `s3://<bucket>/<caminho>` |
| `gs://` | Google Cloud Storage | `gs://<bucket>/<caminho>` |
| `https://` | arquivo público ou com credencial por token | `https://exemplo.org/arquivo.nc` |

- **URI terminada em `/` é um prefixo.** O componente lê e grava só dentro dele. É o que hoje se faz
  com chaves como `azure.allowed-prefix`: o prefixo vira a própria referência.
- **`lake://` nunca leva credencial.** O primeiro segmento é a camada do lake (`bronze`, `silver`,
  `gold`, `staging`, ...). A raiz `/opt/infinitestack/var/lake` só muda em dev local, pela variável
  `APP_LAKE_ROOT`.
- **Sem `credential`, o acesso é anônimo.** Serve para buckets públicos, como os de dados de
  satélite abertos.
- `format` é opcional e só informa (`parquet`, `netcdf`, `grib`, `geojson`, `csv`, `zarr`, `png` ou
  outro texto).

### 5.5 `http`

```json
{ "kind": "http", "url": "https://cds.climate.copernicus.eu/api", "credential": "copernicus-cds" }
```

Para fontes de ingestão que exigem chave de API. Sem `credential`, a chamada é anônima.

---

## 6. Credenciais

A credencial é um **nome** (`credential: "azure-cliente"`), em minúsculas e com hífen. O valor
mora fora do documento, em um lugar que depende da fase (seção 10):

- **Fase 1:** `/opt/infinitestack/etc/data/app-credentials.json`, permissão `600`, um arquivo por
  instância, compartilhado por todos os apps.
- **Fase 2:** `Automate › Secrets` do IS, resolvido pelo host.

Um arquivo compartilhado resolve o caso de dois apps que leem a mesma conta de storage: os dois
apontam para o mesmo nome, em vez de um copiar o arquivo do outro.

### 6.1 Formato do `app-credentials.json` (fase 1)

```jsonc
{
  "credentials": {
    "azure-cliente": {
      "type": "azure-service-principal",
      "tenantId": "…", "clientId": "…", "clientSecret": "…"
    },
    "s3-parceiro": {
      "type": "aws-access-key",
      "accessKeyId": "…", "secretAccessKey": "…", "region": "sa-east-1"
    },
    "copernicus-cds": { "type": "token", "token": "…" }
  }
}
```

| `type` | Campos | Uso |
|---|---|---|
| `azure-service-principal` | `tenantId`, `clientId`, `clientSecret` | `abfss://` |
| `azure-sas` | `sasToken` | `abfss://` |
| `aws-access-key` | `accessKeyId`, `secretAccessKey`, `region`, `sessionToken` (opcional) | `s3://` |
| `gcp-service-account` | `keyFile` (caminho do JSON da service account, também `600`) | `gs://` |
| `token` | `token` | `http`, `https://` |
| `basic` | `username`, `password` | `http` |

### 6.2 Regras

- **Nenhum valor de credencial entra no documento de configuração**, nem nos padrões nem na
  instância. O schema do app não declara chaves como `password`, `secret`, `token` ou `apiKey` nas
  seções livres. Se o parâmetro é secreto, ele vira uma credencial com nome.
- **Credencial não vai em `params` de workflow** (ver
  [AGENT_APPS_WORKFLOWS_COMMUNICATION.md](AGENT_APPS_WORKFLOWS_COMMUNICATION.md), "Armadilhas").
  O pacote resolve o nome sozinho, lendo o mesmo lugar.
- **O `.env` de pacote do Skills Lab deixa de levar segredo.** Ele aparece no `scripts.json` e para
  quem tem acesso ao Skills Lab. Durante a migração o `.env` continua funcionando (seção 12).
- **Credencial resolvida não sai do processo:** não vai para log, para endpoint de diagnóstico nem
  para o front.

---

## 7. O schema do app

Cada app escreve um `app-config.schema.json` em **JSON Schema draft 2020-12**. Ele descreve as
seções livres e diz quais apelidos de `data` são obrigatórios:

```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "atmo-agent-app configuration",
  "x-schemaVersion": 3,
  "type": "object",
  "properties": {
    "data": {
      "type": "object",
      "required": ["gfsForecast", "ifsForecast", "municipalities", "renders"]
    },
    "shared": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "renderWorkflow": { "type": "string", "default": "atmo-render" }
      }
    },
    "app": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "municipalityTolerance": { "type": "number", "exclusiveMinimum": 0, "default": 0.002 }
      }
    },
    "skills": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "atmo-render": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "renderHoursUtc": { "type": "array", "items": { "type": "integer", "minimum": 0, "maximum": 23 } },
            "maxFrames": { "type": "integer", "minimum": 1 },
            "cacheMaxGb": { "type": "number", "minimum": 0 }
          }
        }
      }
    }
  }
}
```

- **O formato de `data` não se repete aqui.** O envelope (seção 15) já valida cada referência. O
  schema do app só diz quais apelidos ele exige e, se quiser, o `kind` aceito de cada um.
- **`additionalProperties: false` nas seções livres.** Chave com erro de digitação na instância
  falha na subida, em vez de ser ignorada em silêncio.
- **`default` documenta, não preenche.** O valor que vale é o do `app-config.json` do pacote. O
  `default` no schema serve a quem lê e à tela de Configurações. Os dois têm que bater, e o
  build pode conferir isso.
- **`x-schemaVersion`** sobe quando uma mudança no schema pode recusar um arquivo de instância que
  valia antes: chave removida ou renomeada, tipo mudado, nova obrigatória sem padrão. O
  `schemaVersion` do `app-config.json` do pacote é igual a ele. A instância não precisa declarar.
  Ao subir a versão, o README do app diz o que o admin precisa ajustar. Se o arquivo da instância
  ficar inválido, o app abre em modo restrito para a correção (seção 8).
- **Sem `$ref` remoto.** Vale a regra de não acessar a rede: os tipos reutilizáveis abaixo são
  copiados para o `$defs` do schema do app.

### 7.1 Tipos reutilizáveis

Copie para o `$defs` do schema do app os que usar:

```json
{
  "$defs": {
    "bbox": {
      "type": "object", "additionalProperties": false,
      "required": ["west", "south", "east", "north"],
      "properties": {
        "west":  { "type": "number", "minimum": -180, "maximum": 180 },
        "south": { "type": "number", "minimum": -90,  "maximum": 90 },
        "east":  { "type": "number", "minimum": -180, "maximum": 180 },
        "north": { "type": "number", "minimum": -90,  "maximum": 90 }
      }
    },
    "point": {
      "type": "object", "additionalProperties": false, "required": ["lat", "lon"],
      "properties": {
        "lat": { "type": "number", "minimum": -90,  "maximum": 90 },
        "lon": { "type": "number", "minimum": -180, "maximum": 180 }
      }
    },
    "yearRange": {
      "type": "object", "additionalProperties": false, "required": ["from"],
      "properties": {
        "from": { "type": "integer", "minimum": 1900 },
        "to":   { "type": "integer", "minimum": 1900 }
      }
    },
    "dateRange": {
      "type": "object", "additionalProperties": false, "required": ["from"],
      "properties": {
        "from": { "type": "string", "format": "date" },
        "to":   { "type": "string", "format": "date" }
      }
    },
    "month": { "type": "integer", "minimum": 1, "maximum": 12 },
    "hourUtc": { "type": "integer", "minimum": 0, "maximum": 23 },
    "cron": { "type": "string", "pattern": "^\\S+( \\S+){4,5}$" }
  }
}
```

Um `to` ausente quer dizer "até hoje". Datas e horas vão em ISO-8601 e em UTC, salvo quando a chave
diz outra coisa.

### 7.2 Como fica o que hoje é texto codificado

| Hoje (`.env`) | No documento |
|---|---|
| `X_UNITS=A,B` + `X_UNIT_NAMES=A:Nome um;B:Nome dois` | `"units": [{ "code": "A", "name": "Nome um" }, { "code": "B", "name": "Nome dois" }]` |
| `X_COLD_BANDS=12,5,2` | `"coldBandsC": [12, 5, 2]` |
| `X_GFS_CYCLES=00,06,12,18` | `"gfs": { "cyclesUtc": [0, 6, 12, 18] }` |
| `X_MAPBIOMAS_YEARS=2017-2025` | `"mapbiomasYears": { "from": 2017, "to": 2025 }` |
| `X_BBOX=-80,-40,10,10` | `"bbox": { "west": -80, "south": -40, "east": 10, "north": 10 }` |
| `X_C3S_CENTRES=ecmwf:51` | `"c3sCentres": [{ "centre": "ecmwf", "system": 51 }]` |
| `X_CLIMATE_SOURCE=mirror:SCHEMA.TABELA` | em `data`: `"climate": { "kind": "mirror", "table": "SCHEMA.TABELA" }` |
| `X_STORAGE=local` + `X_AZURE_ACCOUNT` + `X_AZURE_CONTAINER` + `X_AZURE_PREFIX` | em `data`: `"output": { "kind": "storage", "uri": "abfss://…/prefixo/", "credential": "…" }` |
| `X_AZURE_CREDENTIALS_FILE` + `X_AZURE_CREDENTIALS_PREFIX` | some: a referência leva `credential` |

Prefira um objeto por fonte quando um grupo de chaves só faz sentido junto (`"era5": { "firstYear":
1979, "levelsHpa": [1000, 925, …], "hoursUtc": [0, 6, 12, 18] }`). Isso substitui o prefixo
repetido no nome da variável.

---

## 8. Carga, mescla e validação

Cada componente (o `.ispz` e cada pacote) carrega a configuração **na subida**, nesta ordem:

1. Lê o `app-config.json` que veio no próprio pacote (padrões).
2. Lê o arquivo de instância: `APP_CONFIG_FILE` se definida, senão
   `/opt/infinitestack/etc/data/<plugin_id>.config.json`. **Arquivo ausente é normal**: valem só os
   padrões.
3. Mescla a instância sobre os padrões:
   - **objeto com objeto:** chave a chave, recursivamente;
   - **array, número, texto, booleano:** a instância substitui o valor inteiro. Array não é
     concatenado;
   - **`null` na instância** não é aceito. Para voltar ao padrão, apague a chave.
   - **Uma referência de `data` é substituída inteira**, não mesclada campo a campo. Trocar um
     `table` por um `storage` não pode deixar sobra do tipo anterior.
4. Confere `configVersion` e `pluginId`.
5. Valida o resultado contra o schema do envelope (seção 15) e contra o `app-config.schema.json`.
6. **Se algo não valida,** a mensagem traz o caminho do arquivo e o JSON Pointer do erro (ex.:
   `/opt/infinitestack/etc/data/atmo-agent-app.config.json: /skills/atmo-render/maxFrames: must be >= 1`)
   e vai para o log.
   - **O pacote** sai com código diferente de zero, e a mensagem vai para o log da rodada.
   - **O `.ispz` sobe em modo restrito.** O `runtime-health` responde normalmente, a tela principal
     mostra "configuração inválida" com os erros, as rotas de dados respondem `503`, e só a tela de
     Configurações funciona, para o admin corrigir. Se o `.ispz` não subisse, ninguém conseguiria
     consertar pela tela uma instância que ficou inválida, por exemplo depois de um
     `schemaVersion` novo.
   - **Padrões do pacote inválidos** são erro de build, não de instância: aí o `.ispz` não sobe.
7. Resolve as referências de `data` que o componente usa (seção 10).

**Quando relê.** O `.ispz` carrega na subida e recarrega depois de cada gravação pela tela (seção
9). Uma edição à mão no arquivo só vale depois de reiniciar o app. Um pacote do Skills Lab relê a
cada rodada, porque cada rodada é um processo novo.

**Diagnóstico.** O `GET {base_path}/api/app-config` da seção 9 também serve de diagnóstico: mostra o
documento mesclado, a origem de cada arquivo lido e o estado de cada referência (resolvida,
ausente, erro), **sem nenhuma credencial**.

**Bibliotecas sugeridas.** Java: Jackson (já está no Spring Boot) e
`com.networknt:json-schema-validator`. Python: `jsonschema`. Os dois lados implementam o mesmo
carregador pequeno. Um helper por linguagem, copiado entre apps como já se faz com o
`AppSchema.java`, até virar biblioteca.

---

## 9. Edição pela tela de Configurações

A tela é **do próprio app**: cada app desenha o formulário dos seus parâmetros, na mesma tela do
`isp-index.html` (modal ou painel, ver [design.md](design.md) §1), aberta pelo botão de
Configurações da barra do header (README, "Barra de ações do header"). O contrato abaixo é o mesmo
em todo app: quem pode, como lê, como grava e como duas pessoas não se sobrescrevem.

### 9.1 Quem pode

- Só **`ADMIN`** e **`SCICROP`**, pelo `X-IS-Role` que o proxy do IS põe em cada requisição.
- **O servidor decide**, não o front:
  - o botão nem é desenhado para outros papéis (`th:if` no template);
  - `GET` e `PUT /api/app-config` respondem **`403`** para outros papéis, mesmo chamados à mão.
- Fora do IS (dev local, sem `IS_PLUGIN_INTERNAL_TOKEN`), a requisição sem headers conta como ADMIN
  local, como no `CurrentUserResolver` do `is-plan-seq-agent-app`. Dentro do IS, requisição sem
  `X-IS-User-Id` é recusada.
- `X-IS-Role: ANONYMOUS` (rotas públicas `/p/**`) nunca é admin.

### 9.2 Ler: `GET {base_path}/api/app-config`

```json
{
  "revision": "sha256:9f2c…",
  "instance": { "configVersion": 1, "pluginId": "atmo-agent-app", "skills": { "atmo-render": { "maxFrames": 60 } } },
  "defaults": { "…": "o app-config.json do pacote" },
  "effective": { "…": "padrões + instância, já mesclados" },
  "schema": { "…": "o app-config.schema.json" },
  "credentialNames": ["azure-cliente", "copernicus-cds"],
  "references": { "renders": "ok", "ingestFiles": "ok", "seasonal": "error: table not found" },
  "lastChange": { "by": "maria", "at": "2026-11-15T14:32:10Z" },
  "valid": true,
  "writable": true,
  "restartRequired": false
}
```

- **`revision`** é o SHA-256 do conteúdo do arquivo de instância como está no disco, ou `"absent"`
  quando o arquivo não existe. Vai também no header `ETag`.
- **`credentialNames`** lista só os nomes que existem no `app-credentials.json`, para a tela
  oferecer a escolha. Valor de credencial nunca sai daqui.
- **`lastChange`** vem do histórico (9.5). Sem histórico (arquivo editado à mão), vem `null`.
- **`valid`** é `false` quando o app está em modo restrito (seção 8). Nesse caso a resposta inclui
  `errors`, no mesmo formato do `422`.
- **A rota é `/api/app-config`, não `/api/config`.** Vários apps já usam `GET /api/config` para o
  próprio front, aberto a todo usuário (atmo, is-plan-seq, monitor-oper). Esta rota é só de admin e
  não pode tomar o lugar daquela.

### 9.3 Gravar: `PUT {base_path}/api/app-config`

```
PUT /api/plugins/atmo-agent-app/api/app-config
If-Match: "sha256:9f2c…"
Content-Type: application/json

{ "configVersion": 1, "pluginId": "atmo-agent-app", "skills": { "atmo-render": { "maxFrames": 90 } } }
```

O corpo é o **documento de instância inteiro** (só o que muda em relação aos padrões), não um
patch. O servidor faz, nesta ordem e **segurando a trava** (9.4):

1. Confere o papel. Se não for admin: **`403`**.
2. Exige `If-Match`. Sem ele: **`428`**. Ninguém grava sem dizer qual revisão viu.
3. Recalcula a revisão do arquivo no disco. Se for diferente do `If-Match`: **`409`**, e nada é
   gravado:
   ```json
   { "error": "revision_conflict",
     "revision": "sha256:51ab…",
     "instance": { "…": "o documento que está no disco agora" },
     "lastChange": { "by": "joao", "at": "2026-11-15T14:35:02Z" } }
   ```
4. Mescla com os padrões e valida (envelope e schema do app). Se não valida: **`422`** com a lista
   de erros `{ "pointer": "/skills/atmo-render/maxFrames", "message": "must be >= 1" }`. Nada é
   gravado.
5. Grava de forma atômica (9.4), registra no histórico (9.5) e recarrega a configuração.
6. Responde **`200`** com o mesmo corpo do `GET` e a nova `revision`.

A tela deve tirar da instância as chaves iguais ao padrão antes de mandar. Assim, uma mudança de
padrão numa versão nova do pacote chega à instância que não tinha mexido naquela chave.

### 9.4 Duas pessoas ao mesmo tempo

É **travamento otimista**: ninguém reserva a tela, e quem salva por último só consegue se viu a
versão atual.

```
Maria: GET  → revision A
João:  GET  → revision A
João:  PUT If-Match A → 200, revision B
Maria: PUT If-Match A → 409 (está em B, João salvou às 14:35)
Maria: tela mostra o que João mudou, recarrega em B, ela refaz a alteração dela
Maria: PUT If-Match B → 200, revision C
```

- **A revisão é o hash do conteúdo, não um contador.** Assim também pega a edição feita à mão no
  servidor, ou por qualquer caminho que não passou pelo app.
- **Não há trava de edição** ("Fulano está editando"). Ela fica presa quando alguém fecha a aba
  ou perde a conexão, e exige expiração e um "forçar". Com poucos admins, conflito é raro, e o
  `409` resolve sem estado nenhum.
- **No `409`, a tela não descarta o que a pessoa digitou.** Mostra as diferenças entre o que ela
  viu e o que está no disco, e deixa reaplicar por cima da versão nova. Não há botão de "gravar
  assim mesmo": para sobrescrever, a pessoa recarrega e grava de novo, sabendo o que está
  apagando.
- **A trava:** "comparar a revisão → validar → gravar → registrar" roda sob uma trava em memória
  (o `.ispz` é um processo só por instância) e sob um `FileLock` num arquivo ao lado,
  `<plugin_id>.config.json.lock`. A trava não fica no próprio arquivo de configuração, porque ele
  é substituído pela renomeação.
- **Gravação atômica:** escreve `<plugin_id>.config.json.tmp-<aleatório>` no mesmo diretório,
  `fsync`, e renomeia por cima com `ATOMIC_MOVE`, mantendo a permissão do arquivo anterior. Um pacote
  do Skills Lab que leia durante a gravação vê a versão anterior ou a nova, nunca metade.
- **Granularidade:** uma revisão para o documento inteiro. Se admins mexendo em seções diferentes
  passarem a esbarrar com frequência, a revisão pode passar a ser por seção (`data`, `shared`,
  `app`, `skills.<pacote>`) sem mudar o resto do contrato.

### 9.5 Histórico

Toda gravação pela tela vira uma linha em `apps.<plugin_id_snake>_config_revision`, no banco do
app, seguindo as regras de nome do README:

| Coluna | Tipo | Conteúdo |
|---|---|---|
| `id` | `bigserial` | chave |
| `revision` | `text` | revisão gravada |
| `previous_revision` | `text` | revisão que estava no disco (`absent` na primeira) |
| `document` | `text` | o documento de instância gravado, em JSON |
| `changed_by` | `text` | `X-IS-User-Id` |
| `changed_by_name` | `text` | `X-IS-Username` |
| `changed_at` | `timestamptz` | `now()` |

Índice `idx_<plugin_id_snake>_config_revision_changed_at`. O documento vai em `text`, não `jsonb`,
para não prender o app ao PostgreSQL.

- O histórico alimenta o `lastChange` e o "quem salvou" do `409`.
- **Voltar a uma versão** é carregar o `document` dela na tela e gravar pelo mesmo `PUT`, com
  `If-Match`. Não há rota própria de restauração.
- O arquivo continua sendo a fonte da verdade, porque é ele que os pacotes leem. A tabela é só
  histórico. Se ela falha, a gravação falha junto, para não haver mudança sem registro.

### 9.6 Depois de gravar

- **O `.ispz`** troca a configuração em memória de uma vez (um objeto imutável atrás de um
  `AtomicReference`), e cada requisição lê a configuração do momento.
- **O que guarda estado** (pool de conexão do mirror, cache de arquivo de storage) e não sabe se
  refazer com a configuração nova responde `restartRequired: true`. A tela avisa que a mudança
  vale depois de reiniciar o app.
- **Pacotes do Skills Lab** pegam a configuração nova na próxima rodada. A rodada em curso termina
  com a que leu.

### 9.7 O que a tela não edita

- **Valor de credencial.** A tela escolhe o **nome** entre os `credentialNames`, e o valor continua
  com o operador (fase 1) ou em `Automate › Secrets` (fase 2).
- **A liberação de workflows** (`<plugin_id>-workflows.json`), pelo motivo da seção 13.
- **`configVersion` e `pluginId`**, que a tela manda como recebeu.

### 9.8 Permissão de escrita

O processo do app precisa poder criar e renomear arquivos em `/opt/infinitestack/etc/data/`.
Se não pode, o `GET` responde com `"writable": false` e a tela abre só para leitura, dizendo por
quê. Confirmar essa permissão numa instância real é o primeiro passo da adoção (seção 16).

---

## 10. Fases: o que o app faz hoje e o que passa ao host

O formato do documento é o mesmo nas duas fases. Muda quem resolve as referências e onde as
credenciais moram.

### Fase 1 — convenção, sem mudança no host

| `kind` | Quem resolve e como |
|---|---|
| `table` | o componente, com o datasource que já recebe (`SPRING_DATASOURCE_*` no `.ispz`, o banco do projeto no pacote) |
| `storage` `lake://` | o componente: vira caminho em `/opt/infinitestack/var/lake/` |
| `storage` em nuvem, `http` | o componente, buscando a `credential` no `app-credentials.json` |
| `mirror` | o componente, lendo a conexão do `catalogExplorerMirror.json` |
| `catalog` | o componente, lendo o `metadata` da fonte no `catalogExplorer.json` |

O que a fase 1 já garante: **nenhuma credencial no repo, no pacote, no documento de configuração
nem no `.env` do Skills Lab**, e um lugar só por instância para cada credencial.

O que ela **não** garante: em `mirror` e `catalog`, o processo do app lê o catálogo e vê as
credenciais de todas as fontes, não só da que pediu. Os dois documentos de catálogo estão em
`/opt/infinitestack/etc/data/`. É a mesma exceção que existe hoje para ler o mirror, só que
declarada.

### Fase 2 — o host resolve (proposta, depende de issue no back)

1. **Validação na instalação.** O `plugininstall` valida o `app-config.json` contra o
   `app-config.schema.json` do `.ispz` e recusa o pacote inválido.
2. **Credenciais em `Automate › Secrets`.** O nome em `credential` passa a ser o nome de um segredo
   do IS. O `app-credentials.json` deixa de existir.
3. **Resolução pela porta interna.** O componente pede ao host, com `IS_PLUGIN_INTERNAL_TOKEN`, a
   referência pelo apelido e recebe o mínimo para usá-la: uma URL assinada ou um token de curta
   duração para storage, e uma conexão só leitura da fonte pedida para `mirror` e `catalog`. O app
   deixa de ler os arquivos de catálogo.
4. **Consulta pelo host.** Para `mirror`, o host já tem roteamento de consulta (back#785). Com ele
   exposto aos apps, a consulta sai sem que o app receba credencial nenhuma. É o ponto final desejado
   para dados SQL externos. Para arquivos, a URL assinada do item 3 faz esse papel.

A tela de Configurações continua sendo do app (seção 9) nas duas fases.

Um app escrito para a fase 1 passa para a fase 2 trocando só o resolvedor. O documento, o schema e
os apelidos não mudam.

---

## 11. Empacotamento

No repo do app:

```
<app-repo>/
├── config/
│   ├── app-config.schema.json      fonte única do schema
│   └── app-config.json             fonte única dos padrões
├── agent-app/                      o .ispz
└── skillslab/<pacote>/             o pacote do Skills Lab
```

- O `step2-stage-package.sh` do `.ispz` copia os dois arquivos para
  `package-layout/<plugin_id>/config/` e os inclui no `sha256sum` do `checksums.sha256`, como o
  `plugin-permissions.json`.
- O script que monta o pacote do Skills Lab copia os mesmos dois arquivos para a raiz do pacote.
- O código lê os padrões **do próprio pacote**: no `.ispz`, de `${IS_PLUGIN_INSTALL_PATH}/config/`;
  no pacote, da pasta do script.
- Um app sem pacote do Skills Lab usa o mesmo formato, só sem a seção `skills`.

---

## 12. Migração de um app existente

1. Inventariar as chaves de hoje: `application.properties` (só as do app, não as do contrato com o
   host), `.env` e `config.py` de cada pacote, e o `.properties`/`.env` de instância.
2. Separar em quatro grupos: **dado** (vira `data`), **segredo** (vira `credential`),
   **compartilhado** (vira `shared`) e **próprio** (vira `app` ou `skills.<pacote>`).
3. Trocar todo texto codificado por estrutura (tabela 7.2).
4. Escrever o schema e os padrões em `config/`, e o carregador nos dois lados.
5. **Período de transição:** se o arquivo de instância não existe e as variáveis antigas existem, o
   carregador as lê e loga um aviso de depreciação com a chave nova equivalente. Uma versão depois,
   isso sai. O `.env` com segredo é esvaziado assim que a credencial vai para o
   `app-credentials.json`.
6. Gerar o `<plugin_id>.config.json` de cada instância a partir do que ela usa hoje.

**Fica no `application.properties`** o que é contrato com o host e não muda por instância:
`infinitestack.plugin.*`, `spring.datasource.*` com `${IS_*}`/`${SPRING_DATASOURCE_*}`,
`infinitestack.host.*` e `infinitestack.active-llm.*`. Isso já é injetado pelo IS e este documento
não substitui.

---

## 13. O que não entra neste arquivo

- **Liberação de workflows** (`/opt/infinitestack/etc/<plugin_id>-workflows.json`). Quem lê é o
  host, e quem concede é o operador. O app não pode decidir o que ele mesmo pode disparar, então a
  permissão fica fora do documento que o app grava. O documento pode ter o **slug** do workflow que o
  app usa (`shared.renderWorkflow`), mas a permissão continua lá.
- **Dados de referência do domínio,** como regras de uso de insumos, calendários agronômicos e
  tabelas de parâmetros técnicos. São conteúdo versionado com schema próprio, não configuração de
  instalação.
- **Parâmetros de uma rodada,** que vão em `params` do workflow. O documento guarda o padrão; a
  rodada pode mandar o valor daquela vez.
- **Contrato com o host** (seção 12).

---

## 14. Exemplo completo

Padrões do pacote (`config/app-config.json`) de um app de visualização que lê tabelas de um app de
ingestão e grava painéis no lake:

```json
{
  "configVersion": 1,
  "pluginId": "atmo-agent-app",
  "schemaVersion": 3,
  "data": {
    "municipalities": { "kind": "table", "table": "gold.br_geo_agent_app_ibge_municipality" },
    "gfsForecast":    { "kind": "table", "table": "gold.br_weather_agent_app_gfs_step" },
    "ifsForecast":    { "kind": "table", "table": "gold.br_weather_agent_app_ifs_step" },
    "seasonal":       { "kind": "table", "table": "gold.br_weather_agent_app_c3s_start" },
    "radar":          { "kind": "storage", "uri": "lake://bronze/br-weather-agent-app/redemet/" },
    "renders":        { "kind": "storage", "uri": "lake://gold/atmo-agent-app/renders/" }
  },
  "shared": {
    "renderWorkflow": "atmo-render"
  },
  "app": {
    "municipalityTolerance": 0.002
  },
  "skills": {
    "atmo-render": {
      "renderHoursUtc": [0, 6, 12, 18],
      "maxFrames": 120,
      "cacheMaxGb": 20
    }
  }
}
```

Instância (`/opt/infinitestack/etc/data/atmo-agent-app.config.json`) de um cliente que guarda os
NetCDF de ingestão numa conta Azure e quer menos quadros:

```json
{
  "configVersion": 1,
  "pluginId": "atmo-agent-app",
  "data": {
    "ingestFiles": {
      "kind": "storage",
      "uri": "abfss://dados@contacliente.dfs.core.windows.net/infinitestack/br-weather-agent-app/",
      "credential": "azure-cliente",
      "format": "netcdf"
    }
  },
  "skills": {
    "atmo-render": { "maxFrames": 60 }
  }
}
```

E em `/opt/infinitestack/etc/data/app-credentials.json` (permissão `600`) existe uma entrada
`azure-cliente` do tipo `azure-service-principal`, que o app de ingestão também usa para gravar.

---

## 15. Referência: schema do envelope v1

Valida a estrutura comum e cada referência de `data`. As seções livres são validadas pelo schema
do app.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "infinitestack/app-config/envelope/v1",
  "title": "InfiniteStack Agent App configuration document, envelope v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["configVersion", "pluginId"],
  "properties": {
    "$schema": { "type": "string" },
    "configVersion": { "const": 1 },
    "pluginId": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$" },
    "schemaVersion": { "type": "integer", "minimum": 1 },
    "data": {
      "type": "object",
      "propertyNames": { "pattern": "^[a-z][A-Za-z0-9]*$" },
      "additionalProperties": { "$ref": "#/$defs/dataRef" }
    },
    "shared": { "type": "object" },
    "app": { "type": "object" },
    "skills": {
      "type": "object",
      "propertyNames": { "pattern": "^[a-z0-9][a-z0-9-]*$" },
      "additionalProperties": { "type": "object" }
    }
  },
  "$defs": {
    "qualifiedTable": {
      "type": "string",
      "pattern": "^[A-Za-z_][A-Za-z0-9_]*\\.[A-Za-z_][A-Za-z0-9_]*$"
    },
    "mirrorTable": {
      "type": "string",
      "pattern": "^[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z_][A-Za-z0-9_]*){1,2}$"
    },
    "credentialName": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$" },
    "description": { "type": "string" },
    "dataRef": {
      "oneOf": [
        { "$ref": "#/$defs/tableRef" },
        { "$ref": "#/$defs/mirrorRef" },
        { "$ref": "#/$defs/catalogRef" },
        { "$ref": "#/$defs/storageRef" },
        { "$ref": "#/$defs/httpRef" }
      ]
    },
    "tableRef": {
      "type": "object", "additionalProperties": false, "required": ["kind", "table"],
      "properties": {
        "kind": { "const": "table" },
        "table": { "$ref": "#/$defs/qualifiedTable" },
        "description": { "$ref": "#/$defs/description" }
      }
    },
    "mirrorRef": {
      "type": "object", "additionalProperties": false, "required": ["kind", "table"],
      "properties": {
        "kind": { "const": "mirror" },
        "table": { "$ref": "#/$defs/mirrorTable" },
        "source": { "type": "string", "minLength": 1 },
        "description": { "$ref": "#/$defs/description" }
      }
    },
    "catalogRef": {
      "type": "object", "additionalProperties": false, "required": ["kind", "source"],
      "properties": {
        "kind": { "const": "catalog" },
        "source": { "type": "string", "minLength": 1 },
        "table": { "$ref": "#/$defs/qualifiedTable" },
        "description": { "$ref": "#/$defs/description" }
      }
    },
    "storageRef": {
      "type": "object", "additionalProperties": false, "required": ["kind", "uri"],
      "properties": {
        "kind": { "const": "storage" },
        "uri": { "type": "string", "pattern": "^(lake|abfss|s3|gs|https)://\\S+$" },
        "credential": { "$ref": "#/$defs/credentialName" },
        "format": { "type": "string", "minLength": 1 },
        "description": { "$ref": "#/$defs/description" }
      },
      "if": { "properties": { "uri": { "pattern": "^lake://" } } },
      "then": { "not": { "required": ["credential"] } }
    },
    "httpRef": {
      "type": "object", "additionalProperties": false, "required": ["kind", "url"],
      "properties": {
        "kind": { "const": "http" },
        "url": { "type": "string", "pattern": "^https://\\S+$" },
        "credential": { "$ref": "#/$defs/credentialName" },
        "description": { "$ref": "#/$defs/description" }
      }
    }
  }
}
```

---

## 16. Decisões em aberto

As decisões abaixo foram tomadas nesta proposta e podem ser revistas antes da adoção:

1. **Alcance das credenciais.** A fase 1 tira as credenciais dos arquivos, do repo e do `.env`, mas
   o processo do app ainda as recebe. A meta proposta é a fase 2: o host resolve a referência e, no
   mirror, faz a consulta. Fica por decidir se o host expõe o roteamento de consulta (back#785) aos
   apps ou só entrega conexões de curta duração.
2. **Papel do host.** A proposta começa como convenção, com cada componente validando na subida e o
   `.ispz` validando antes de gravar. A validação na instalação fica para a fase 2. A tela de
   Configurações é do app, não do host.
3. **Um arquivo de credenciais por instância, compartilhado entre apps.** Evita cópia de segredo
   entre apps. Não isola um app do outro, mas os apps já rodam no mesmo contêiner (ver a nota da
   seção 4 do guia de workflows).
4. **Arquivo de instância ausente é válido.** Facilita instalar sem configurar. Um app cujo
   `data` obrigatório não tem padrão possível abre em modo restrito (seção 8) até o admin preencher.
5. **Sem override por variável de ambiente por chave.** Só `APP_CONFIG_FILE` e `APP_LAKE_ROOT`,
   para dev local. Override por chave traria de volta o texto codificado.
6. **Travamento otimista, revisão do documento inteiro.** Escolhido em vez de trava de edição
   (seção 9.4). Revisão por seção fica como evolução, se o conflito deixar de ser raro.
7. **O app grava em `/opt/infinitestack/etc/data/`.** Falta confirmar numa instância real que o
   processo do app tem permissão de escrita ali (seção 9.8). Se não tiver, a alternativa é o host
   criar o arquivo de instância com o dono certo na instalação do app.
