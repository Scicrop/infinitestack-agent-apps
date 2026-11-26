# Como criar um Agent App em Python (FastAPI)

Como fazer um Agent App em **Python**: um app ASGI (FastAPI, Starlette ou outro) empacotado como
`.ispz`, que o IS instala, sobe, protege e mostra como qualquer Agent App. Não há Spring, jar nem
Thymeleaf. Mudam o que vai dentro do `.ispz` e como o host executa o app. Continuam iguais o proxy
autenticado em `/api/plugins/<id>/`, o RBAC por app, a retenção (`appstop`), o log, o Process
Explorer e as rotas públicas.

> Requer um back do IS com a `infinitestack-back#1416` (fase 0 da `infinitestack-infra#293`). Num
> back sem ela, o `plugininstall` recusa o pacote com `Manifest field runtime must be "jvm" or
> "native"`.
>
> Exemplo completo e testado: [`python-demo-app/`](python-demo-app/). Mostra quem está logado, um
> contador por SSE e um eco por WebSocket.

---

## Índice

1. [Como funciona](#1-como-funciona)
2. [Estrutura do pacote](#2-estrutura-do-pacote)
3. [`plugin-manifest.json`](#3-plugin-manifestjson)
4. [O app](#4-o-app)
5. [Quem está chamando: `X-IS-Identity`](#5-quem-está-chamando-x-is-identity)
6. [Chamar o IS](#6-chamar-o-is)
7. [Streaming, SSE e WebSocket](#7-streaming-sse-e-websocket)
8. [Memória](#8-memória)
9. [Build e instalação](#9-build-e-instalação)
10. [Testar fora do IS](#10-testar-fora-do-is)
11. [Erros comuns](#11-erros-comuns)
12. [Checklist](#12-checklist)

---

## 1. Como funciona

```
navegador ─► IS: proxy /api/plugins/<id>/**  (login nativo ou OAuth, canOpenApp, X-IS-Identity)
                 │  127.0.0.1:<porta dinâmica>
                 ▼
            is_app_host.py (do IS) ─► uvicorn ─► seu app ASGI, montado no base_path
```

Na instalação, o IS valida o pacote e cria um **ambiente virtual por versão**
(`<instalação>/.venv`), com `pip install -r app/requirements.txt`. O pip escreve no log do app. Se
algum requisito não instala, a instalação falha com o motivo do pip e a versão é removida.

Ao subir, o IS roda o seu app com o **launcher do host** (`is_app_host.py`), que:

- importa o objeto ASGI de `python.entrypoint`;
- monta o app no `base_path`. O app é escrito a partir de `/`: o proxy encaminha
  `/api/plugins/<id>/hello` e a rota do app é `/hello`. O `request.url`, os redirects e o
  `/docs` saem com o prefixo certo;
- responde `GET <base_path>/api/runtime-health` quando o app terminou de importar e o *lifespan*
  rodou. É isso que o IS espera antes de mandar tráfego, então o app **não** implementa o health check;
- vigia o teto de memória ([seção 8](#8-memória)).

O ambiente é reaproveitado enquanto o `requirements.txt`, as wheels e o interpretador forem os
mesmos. Uma versão nova do app tem um ambiente novo, e desinstalar a versão apaga o dela.

O launcher e o SDK `infinitestack_app` vêm do IS, copiados para o ambiente a cada subida. Não
os coloque no `requirements.txt`.

---

## 2. Estrutura do pacote

```
python-demo-app/                   ← pasta raiz do .ispz = plugin_id
├── plugin-manifest.json
├── checksums.sha256               ← gerado no build
├── config/
│   └── plugin-permissions.json
└── app/
    ├── main.py                    ← python.entrypoint "main:app"
    ├── requirements.txt           ← obrigatório; inclui uvicorn
    └── wheels/                    ← opcional: instância sem internet (seção 9)
```

Diferenças para o app JVM: não há `app/plugin.jar`, `app/launch.properties` nem
`web/templates/isp-*.html`. As páginas são rotas do próprio app. `/` é a página principal e
`/status` a de status, os dois links que o `plugininstall` mostra.

---

## 3. `plugin-manifest.json`

```json
{
  "plugin_id": "python-demo-app",
  "name": "Python Demo App",
  "version": "0.1.0",
  "description": "FastAPI example: who is signed in, server-sent events and a WebSocket echo.",
  "base_path": "/api/plugins/python-demo-app",
  "runtime": "python",
  "python": { "entrypoint": "main:app" },
  "supported_destination_databases": ["postgres", "oracle"],
  "requires_host_authentication": true,
  "requires_host_authorization": true,
  "requires_host_datasource": true,
  "allows_own_user_store": false,
  "allows_own_datasource": false,
  "resources": { "max_heap_mb": 256 }
}
```

| Campo | Python |
|---|---|
| `runtime` | `"python"` |
| `python.entrypoint` | `módulo:atributo`, relativo a `app/`. `main:app` é a variável `app` de `app/main.py`; `web:app` aceita `app/web/__init__.py` |
| `python.requirements` | opcional; padrão `app/requirements.txt`, sempre dentro de `app/` |
| `entrypoint` | não se usa (é a classe main de um app JVM) |
| `web` | opcional; se vier, `local_assets_only` não pode ser `false` |
| `resources.max_heap_mb` | **teto da memória real (RSS)** do processo, não um heap ([seção 8](#8-memória)) |
| `supported_destination_databases` | `postgres`, `oracle`, `sqlserver`, como em todo app |

O resto (`requires_host_*`, `allows_own_*`, `accepts_service_tokens`, `public_routes`,
`gold_tables`) vale como no [README.md](README.md).

---

## 4. O app

`app/requirements.txt`:

```
fastapi>=0.109
uvicorn>=0.30
websockets>=12        # só se o app usa WebSocket
```

Use **FastAPI 0.109 ou mais novo** (Starlette 0.35+). O launcher passa o `base_path` como
`root_path` do ASGI, e versões antigas do Starlette não roteiam assim.

`app/main.py`:

```python
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from infinitestack_app import Identity, is_user

app = FastAPI(title="Meu App")

@app.get("/", response_class=HTMLResponse)
def index():
    return "<h1>Meu App</h1>"

@app.get("/status", response_class=HTMLResponse)
def status():
    return "<p>OK</p>"

@app.get("/me")
def me(user: Identity = Depends(is_user)):
    return {"username": user.username, "role": user.role}
```

Na página, monte URLs a partir de `location.pathname` (o exemplo faz isso), nunca com
`/api/plugins/<id>` fixo no código.

Regras, como em todo app:

- assets locais: nada de CDN;
- credenciais vêm do IS por variável de ambiente, nunca do código;
- estado do app no schema `apps`, com prefixo do `plugin_id`; análise em `gold`;
- nada gravado no disco fora de `/tmp`: a pasta de instalação é da versão.

Variáveis que o IS injeta (as mesmas de um app JVM, mais as do Python):

| Variável | O quê |
|---|---|
| `IS_PLUGIN_ID`, `IS_PLUGIN_BASE_PATH`, `IS_PLUGIN_INSTALL_PATH` | identificação do app |
| `IS_HOST_BASE_URL`, `IS_PLUGIN_INTERNAL_TOKEN` | chamar a API interna do IS ([seção 6](#6-chamar-o-is)) |
| `IS_APP_IDENTITY_KEY` | chave que verifica o `X-IS-Identity` ([seção 5](#5-quem-está-chamando-x-is-identity)) |
| `IS_DESTINATION_DB`, `SPRING_DATASOURCE_URL/USERNAME/PASSWORD`, `ORACLE_DATASOURCE_*` | banco de destino. A URL é JDBC: para Python, troque `jdbc:postgresql://` por `postgresql://` |
| `IS_ACTIVE_LLM_PROVIDER`, `IS_ACTIVE_LLM_MODEL`, `IS_ACTIVE_LLM_CREDENTIAL_KEY` | LLM ativa |
| `IS_APP_PORT`, `IS_APP_MAX_MEMORY_MB`, `IS_PYTHON_ENTRYPOINT` | lidos pelo launcher |

---

## 5. Quem está chamando: `X-IS-Identity`

Toda requisição que o proxy encaminha traz `X-IS-Identity`: um JWT (HS256) assinado pelo IS com
uma chave que só ele e o seu app conhecem (`IS_APP_IDENTITY_KEY`, nova a cada subida). O token
vale 60 segundos e tem o app como audiência. Login nativo, OAuth (Azure AD) e token de serviço
(`isk_`) chegam do mesmo jeito.

Confie nele, e não nos cabeçalhos `X-IS-User-Id`/`X-IS-Role`. Esses continuam vindo, por
compatibilidade, mas não podem ser verificados: valem só enquanto o app escuta em 127.0.0.1. Numa
fase seguinte o app pode rodar em outro container ou outra máquina, e aí só o token é confiável.
O IS descarta todo `X-IS-*` que venha do navegador.

O SDK faz a verificação, só com a biblioteca padrão:

```python
from fastapi import Depends
from infinitestack_app import Identity, is_user, is_caller, require_roles

@app.get("/dados")
def dados(user: Identity = Depends(is_user)):           # 401 sem token válido ou anônimo
    ...

@app.post("/admin", dependencies=[Depends(require_roles("ADMIN"))])  # 403 para outros papéis
def admin(): ...

@app.get("/p/publico")
def publico(caller: Identity = Depends(is_caller)):     # aceita o anônimo das rotas públicas
    ...
```

| `Identity` | |
|---|---|
| `user_id`, `username` | `None` para o anônimo |
| `role` | `ADMIN`, `SCICROP`, `USER`, `SERVICE` ou `ANONYMOUS` |
| `principal_type` | `user`, `service` ou `anonymous`; também `is_user`, `is_service`, `is_anonymous` |

Fora do FastAPI, use `verify_identity(token)` ou `identity_from_headers(headers)`: devolvem a
`Identity` ou lançam `IdentityError`.

---

## 6. Chamar o IS

```python
from infinitestack_app import ISClient

tables = ISClient().get("/api/extensions/internal/catalog/tables")
```

O `ISClient` manda `X-IS-Plugin-Id` e `X-IS-Plugin-Internal-Token` para `IS_HOST_BASE_URL`. Os
endpoints são os mesmos de um app JVM: catálogo, workflows, LLM, diretório. Ver
[AGENT_APPS_WORKFLOWS_COMMUNICATION.md](AGENT_APPS_WORKFLOWS_COMMUNICATION.md).

---

## 7. Streaming, SSE e WebSocket

O proxy repassa a resposta do app **enquanto ela é escrita** (`infinitestack-back#1417`). Um
`StreamingResponse` ou SSE chega evento a evento, e um download grande não passa pela memória do
back. O nginx da instância não segura `/api/plugins/**` (infra#293).

WebSocket funciona no mesmo endereço (`wss://<IS>/api/plugins/<id>/ws`), com a mesma regra de
acesso do HTTP. O handshake precisa vir das páginas do próprio IS (Origin), e o app recebe o
`X-IS-Identity` no handshake:

```python
from fastapi import WebSocket
from infinitestack_app import IdentityError, identity_from_headers

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    try:
        user = identity_from_headers(websocket.headers)
    except IdentityError:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    ...
```

O uvicorn só fala WebSocket com `websockets` (ou `wsproto`) no `requirements.txt`. Subprotocolos
(`Sec-WebSocket-Protocol`) não são repassados.

---

## 8. Memória

`resources.max_heap_mb` é o teto da **memória real (RSS)** do processo, a mesma regra do teto dos
scripts do Skills Lab. O launcher confere a cada 5 segundos. Acima do teto, ele manda SIGTERM
(uvicorn encerra limpo) e, depois de 15 s, SIGKILL. O log do app diz quanto passou, e o app sobe de
novo na próxima requisição. Não é limite de memória virtual: Python com numpy reserva bem mais
endereço do que usa, e esse limite derrubaria apps saudáveis.

Sem `max_heap_mb`, vale o padrão de **Limites de recursos** (`proclimits -app-heap`) ou a fatia do
contêiner. Referência: o `python-demo-app` ocupa ~51 MB de RSS, contra ~250 MB de um app JVM e
~118 MB de um nativo.

---

## 9. Build e instalação

```sh
./python-demo-app/scripts/build-ispz.sh          # gera checksums.sha256 e out/<id>-<versão>.ispz
```

O script só gera os checksums e zipa. Não compila nada.

Instale como qualquer `.ispz`: **Admin › Settings › File Manager**, pasta `staging/`, e depois:

```sh
iscli -c "plugininstall -path /opt/infinitestack/var/lake/staging/python-demo-app-0.1.0.ispz"
```

A instalação demora o tempo do `pip install`: segundos com cache, alguns minutos na primeira vez
com pacotes grandes. O andamento aparece em `iscli -c "lslog -app <plugin_id>"`.

**Instância sem internet:** ponha as wheels em `app/wheels/`. Com a pasta presente, o IS instala só
dela (`--no-index`). Gere as wheels para a plataforma do contêiner do IS (Linux x86_64, Python 3.11):

```sh
pip download -r app/requirements.txt -d app/wheels \
  --platform manylinux2014_x86_64 --python-version 3.11 --only-binary=:all:
```

---

## 10. Testar fora do IS

O app é ASGI comum. Para rodá-lo direto, sem o proxy:

```sh
cd python-demo-app/package/python-demo-app/app
python -m venv .venv && .venv/bin/pip install -r requirements.txt
PYTHONPATH=<infinitestack-back>/src/main/resources/python-app-host .venv/bin/uvicorn main:app --reload
```

As rotas com `Depends(is_user)` respondem 401 sem o `X-IS-Identity`, como devem. Para testá-las,
gere um token com `IS_APP_IDENTITY_KEY` e `IS_PLUGIN_ID` de teste, ou faça override da dependência
no `TestClient`:

```python
app.dependency_overrides[is_user] = lambda: Identity({"sub": "u1", "username": "ana", "role": "ADMIN",
                                                      "principal_type": "user"})
```

---

## 11. Erros comuns

| Mensagem | Causa |
|---|---|
| `Missing required package entry: app/requirements.txt` | sem `requirements.txt`, ou em outro caminho sem `python.requirements` |
| `python.entrypoint names the module X, but the package has neither app/X.py nor app/X/__init__.py` | o módulo do `entrypoint` não está em `app/` |
| `pip could not install app/requirements.txt (exit 1): ...` | requisito inexistente, versão que não tem wheel para Python 3.11, ou instância sem internet e sem `app/wheels/` |
| `app/requirements.txt must include uvicorn` | o host roda o app com uvicorn |
| `Plugin runtime did not become responsive in time` | o app não terminou de importar em 90 s, ou quebrou ao importar: veja `lslog -app <id>` |
| rotas dão 404 com o prefixo certo | FastAPI anterior a 0.109 (Starlette < 0.35) |
| WebSocket fecha na hora com 1006 | falta `websockets` no `requirements.txt`, ou a página veio de outra origem |

---

## 12. Checklist

- [ ] `runtime: "python"` e `python.entrypoint` no manifest; `plugin_id` igual à pasta raiz
- [ ] `app/requirements.txt` com `fastapi>=0.109` e `uvicorn`; `websockets` se usar WebSocket
- [ ] rotas a partir de `/`; `/` e `/status` respondem
- [ ] identidade só por `X-IS-Identity` (`is_user`, `require_roles`, `identity_from_headers`)
- [ ] nenhuma credencial no código; assets locais; nada gravado fora de `/tmp`
- [ ] `resources.max_heap_mb` medido com folga sobre o RSS em uso
- [ ] `scripts/build-ispz.sh` gerou `checksums.sha256`; versão nova a cada mudança
