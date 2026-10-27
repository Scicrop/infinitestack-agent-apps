# Agent App ↔ Workflows do IS

Como fazer o **backend Java** de um Agent App iniciar um workflow do InfiniteStack, mandar
parâmetros até o script Python que ele roda, acompanhar a saída e saber quando a rodada terminou —
e como parar uma rodada no meio.

> Recurso do `infinitestack-back#1280`. A instância precisa estar numa versão do back que tenha a
> porta `/api/extensions/internal/workflows`. Sem ela, toda chamada responde `404`.

---

## Índice

1. [A ideia em um parágrafo](#1-a-ideia-em-um-parágrafo)
2. [O que pode e o que não pode](#2-o-que-pode-e-o-que-não-pode)
3. [Passo 1 — o workflow e o script Python](#3-passo-1--o-workflow-e-o-script-python)
4. [Passo 2 — liberar o workflow para o app](#4-passo-2--liberar-o-workflow-para-o-app)
5. [Passo 3 — o cliente Java](#5-passo-3--o-cliente-java)
6. [Passo 4 — iniciar e esperar o fim da rodada](#6-passo-4--iniciar-e-esperar-o-fim-da-rodada)
7. [Referência da porta](#7-referência-da-porta)
8. [Erros e o que cada um quer dizer](#8-erros-e-o-que-cada-um-quer-dizer)
9. [Armadilhas](#9-armadilhas)
10. [Testar na mão](#10-testar-na-mão)

---

## 1. A ideia em um parágrafo

O app roda como um processo Java **dentro do contêiner do back do IS**. O host injeta no ambiente
dele o endereço local do back (`IS_HOST_BASE_URL`, sempre `http://127.0.0.1:<porta>`) e um token
que só aquele processo conhece (`IS_PLUGIN_INTERNAL_TOKEN`). Com os dois, o backend do app chama a
porta interna `/api/extensions/internal/workflows`, que inicia uma rodada **igual** à do botão
"run" da tela de Schedules: ela aparece em *Observe › Workloads*, no `lsruns`, tem log, medição de
memória e passa pela fila do `proclimits`. O que o app ganha a mais é mandar `params`, que chegam
ao `--context` do script Python daquela rodada.

```
navegador ──(proxy /api/plugins/<app>/**, usuário logado)──▶ backend do app
                                                                │  X-IS-Plugin-Id
                                                                │  X-IS-Plugin-Internal-Token
                                                                ▼
                                            127.0.0.1 /api/extensions/internal/workflows
                                                                │
                                         runTrigger → is_launcher.jar → WorkflowManager
                                                                │  params mesclados no input
                                                                ▼     do 1º bloco executável
                                            python script.py --context '{"year": 2026, ...}'
```

---

## 2. O que pode e o que não pode

| Pode | Não pode |
|---|---|
| Listar, iniciar, acompanhar e parar rodadas dos workflows **liberados** para o app | Mexer em workflow não liberado — nem saber se uma rodada dele existe |
| Mandar `params` por rodada, sem alterar o `workflows.json` | Usar `params` para segredo — eles ficam gravados no registro da rodada |
| Dizer em nome de qual usuário do IS a rodada foi pedida (`onBehalfOf`) | Chamar a porta **pelo front do app**: ela só aceita chamada de `127.0.0.1` sem cabeçalho de proxy, e o token nunca pode chegar ao navegador |
| Criar e editar workflow? **Não** — isso continua na tela ou no CLI | Chamar a porta de fora do contêiner: o nginx bloqueia e o back recusa |

---

## 3. Passo 1 — o workflow e o script Python

O workflow é criado no IS como qualquer outro (tela, ou `mkworkflow` no CLI). Os `params` da
rodada são mesclados no `input` do **primeiro bloco executável** do workflow — o primeiro bloco
`Script`, `Database` ou `Package`, o mesmo que o `addinvarworkflow` usa. Num workflow de um bloco
só, que é o caso comum, é aquele bloco.

A mescla é chave a chave: o que o app manda **sobrescreve** a chave de mesmo nome que estiver
salva no bloco, e o resto do `input` salvo continua lá. Vale só para aquela rodada; a próxima
começa de novo do que está salvo.

O script lê como já lê hoje, pelo `--context`:

```python
import json
from infinitestack import collect, utils

context = json.loads(utils.get_option("context") or "{}")

year = context.get("year", 2025)          # número chega como número
dry_run = context.get("dryRun", False)    # booleano chega como booleano

print(f"processing year {year}")          # vai para o log da rodada, que o app pode ler

# Opcional: devolver um resultado estruturado para blocos seguintes do workflow.
collect.return_data({"rows": 1234, "year": year})
```

Tudo que o script imprime vai para o log da rodada, que o app lê pela porta (seção 6). O
`return_data` serve aos **blocos seguintes do workflow**; o app não lê esse objeto diretamente
— se ele precisa de um resultado, o caminho é o script gravar numa tabela `gold` ou o app ler o log.

---

## 4. Passo 2 — liberar o workflow para o app

A permissão mora **na instância**, não no `.ispz`: o `projectId` e o slug do workflow mudam de um
cliente para outro. Quem instala o app cria um arquivo com o `plugin_id` dele:

```
/opt/infinitestack/etc/<plugin_id>-workflows.json
```

```json
{
  "workflows": [
    { "projectId": "6f1c2e0a-...", "workflow": "daily-crop-report" },
    { "projectId": "6f1c2e0a-...", "workflow": "recalculate-season" }
  ]
}
```

- **Sem o arquivo, nada é permitido.** Arquivo com JSON inválido ou lista vazia também não
  permite nada (e o erro vai para o log do IS dizendo qual arquivo).
- O par `projectId` + `workflow` é a permissão. O mesmo slug em outro projeto não está liberado.
- O arquivo é lido **a cada chamada**: editar vale na hora, sem reiniciar nada.
- O `workflow` é a chave do workflow no `workflows.json` do projeto — o que aparece em
  `iscli -c "lsworkflows -p <projectId>"`. O `projectId` sai de `iscli -c "lsprojects"`.

> O arquivo evita que uma instância **não configurada** deixe o app disparar qualquer coisa. Ele
> não é isolamento contra app malicioso: o app roda no mesmo contêiner. App instalado continua
> sendo código aprovado.

Nunca deixe o app criar esse arquivo ele mesmo. Quem concede é o operador da instância.

---

## 5. Passo 3 — o cliente Java

As três propriedades já estão no `application.properties` padrão (ver README):

```properties
infinitestack.host.base-url=${IS_HOST_BASE_URL:http://127.0.0.1:8081}
infinitestack.plugin.internal-token=${IS_PLUGIN_INTERNAL_TOKEN:}
infinitestack.plugin.runtime-id=${IS_PLUGIN_ID:meu-agent-plugin}
```

Um cliente mínimo com o `RestClient` do Spring:

```java
@Service
public class HostWorkflowClient {

    private final RestClient http;

    public HostWorkflowClient(@Value("${infinitestack.host.base-url}") String hostBaseUrl,
                              @Value("${infinitestack.plugin.runtime-id}") String pluginId,
                              @Value("${infinitestack.plugin.internal-token}") String internalToken) {
        this.http = RestClient.builder()
                .baseUrl(hostBaseUrl + "/api/extensions/internal/workflows")
                .defaultHeader("X-IS-Plugin-Id", pluginId)
                .defaultHeader("X-IS-Plugin-Internal-Token", internalToken)
                .build();
    }

    /** Starts a run and returns its triggerId. */
    public String startRun(String projectId, String workflow, Map<String, Object> params, String onBehalfOf) {
        Map<String, Object> body = new HashMap<>();
        body.put("params", params);
        body.put("onBehalfOf", onBehalfOf);
        Map<?, ?> response = http.post()
                .uri("/projects/{p}/workflows/{w}/runs", projectId, workflow)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(Map.class);
        return (String) response.get("triggerId");
    }

    /** Status of a run; "done" and "result" are the fields to decide on. */
    public Map<String, Object> getRun(String projectId, String triggerId) {
        return http.get().uri("/projects/{p}/runs/{t}", projectId, triggerId)
                .retrieve().body(new ParameterizedTypeReference<>() {});
    }

    /** A slice of the run's log from a byte offset; call again with "next" to follow it. */
    public Map<String, Object> getOutput(String projectId, String triggerId, long from) {
        return http.get().uri("/projects/{p}/runs/{t}/output?from={f}", projectId, triggerId, from)
                .retrieve().body(new ParameterizedTypeReference<>() {});
    }

    /** Stops a running run; false when it had already ended (409 from the host). */
    public boolean stopRun(String projectId, String triggerId) {
        return http.post().uri("/projects/{p}/runs/{t}/stop", projectId, triggerId)
                .exchange((request, response) -> response.getStatusCode().is2xxSuccessful());
    }
}
```

Regras que valem para qualquer cliente:

- **O token não sai do backend do app.** Não vai para template, não vai para resposta de API do
  app, não vai para log.
- **Use sempre `IS_HOST_BASE_URL`.** Não troque por nome de contêiner nem por IP da rede Docker:
  a porta só aceita loopback.
- O `onBehalfOf` é o usuário que pediu a rodada no app. O proxy do IS já entrega esse id ao app no
  cabeçalho `X-IS-User-Id` de cada request do navegador:

  ```java
  @PostMapping("${infinitestack.plugin.base-path}/api/reports/run")
  public Map<String, Object> run(@RequestHeader(value = "X-IS-User-Id", required = false) String userId,
                                 @RequestBody Map<String, Object> form) {
      String triggerId = client.startRun(projectId, "daily-crop-report", Map.of("year", form.get("year")), userId);
      return Map.of("triggerId", triggerId);
  }
  ```

  O host grava esse usuário no registro da rodada e aplica a ele a mesma regra de acesso a agentes
  da tela: se o workflow roda um agente que esse usuário não pode usar, a rodada é recusada.
  Rodada disparada sem usuário (um agendamento interno do app, por exemplo) vai sem `onBehalfOf`.

---

## 6. Passo 4 — iniciar e esperar o fim da rodada

`POST .../runs` responde `202` assim que a rodada é **disparada** — não quando termina. Para saber
o fim, o app consulta `GET .../runs/{triggerId}` de tempos em tempos.

### Os dois campos que decidem

| Campo | Significado |
|---|---|
| `done` | `false` enquanto a rodada está na fila ou rodando; `true` quando acabou, por qualquer motivo |
| `result` | `QUEUED`, `RUNNING` (com `done: false`); `SUCCESS`, `WARNING`, `FAILED`, `INTERRUPTED`, `UNKNOWN` (com `done: true`) |

- `WARNING` é sucesso com aviso que o script marcou (ex.: tabela gold que não pôde ser catalogada) —
  os avisos vêm em `workflow_run.warnings`.
- `INTERRUPTED` é rodada parada (pelo app, pela tela ou pelo `stoprun`) ou morta por reinício do back.
- `UNKNOWN` quer dizer que o workflow foi iniciado e não reportou resultado. Trate como falha a
  investigar, não como sucesso.

**Não decida pelo `exit_code` do registro.** Ele é o código de saída do `is_launcher.jar`, que só
dispara o workflow e sai em segundos. O resultado do script está em `workflow_run`
(`status`, `exitCode`, `log`), e o `result` já faz essa leitura por você.

### Exemplo de espera

```java
public Map<String, Object> runAndWait(String projectId, String workflow, Map<String, Object> params,
                                      Duration timeout) throws InterruptedException {
    String triggerId = client.startRun(projectId, workflow, params, null);
    Instant deadline = Instant.now().plus(timeout);
    long offset = 0;

    while (true) {
        // Follow the log while waiting (optional).
        Map<String, Object> slice = client.getOutput(projectId, triggerId, offset);
        if (Boolean.TRUE.equals(slice.get("exists"))) {
            System.out.print(slice.get("content"));
            offset = ((Number) slice.get("next")).longValue();
        }

        Map<String, Object> run = client.getRun(projectId, triggerId);
        if (Boolean.TRUE.equals(run.get("done"))) {
            return run;  // run.get("result"): SUCCESS, WARNING, FAILED, INTERRUPTED or UNKNOWN
        }
        if (Instant.now().isAfter(deadline)) {
            client.stopRun(projectId, triggerId);   // gave up: do not leave it running unattended
            throw new IllegalStateException("Run " + triggerId + " did not finish within " + timeout);
        }
        Thread.sleep(3000);
    }
}
```

Recomendações:

- **Intervalo de 3 a 5 segundos.** É o que a tela do Skills Lab usa. Rodada de horas não precisa
  de consulta a cada segundo.
- **Não segure um request do navegador esperando.** Para rodada longa, o endpoint do app devolve o
  `triggerId` na hora e o front do app consulta o **backend do app** (que consulta o host). Nunca o
  front direto no host.
- **Guarde o `triggerId`** (numa tabela `apps.<plugin_id>_...`) se o app precisa lembrar das
  rodadas depois de reiniciar.
- **Leitura do log por offset:** `GET .../output?from=<n>` devolve `content`, `next` (o offset para
  a próxima chamada), `more` (se já há mais bytes) e `running`. Repetir com `from=next` acompanha a
  rodada sem reler o que já veio. `exists: false` é normal no começo, antes da primeira linha.

### Rodada que o app não iniciou (agendamento, tela Schedules, CLI)

O app só tem o `triggerId` das rodadas que ele mesmo iniciou. Para mostrar se o workflow está
rodando quando a rodada veio de um agendamento, da tela ou do `runworkflow`, **não falta rota na
porta**: o caminho já existe e combina duas entregas do back.

1. **O script grava o próprio `triggerId`** (`infinitestack-back#1276`). Todo script Python rodado
   pelo IS recebe o id da rodada em `IS_TRIGGER_ID`. Numa rodada de workflow, é o `triggerId` da
   rodada do workflow, o mesmo que a porta conhece. Logo no início, antes de qualquer etapa
   demorada, o script grava esse id numa tabela de controle do app, com o projeto e a hora de
   início:

   ```python
   import os
   from pathlib import Path

   run_id = os.environ.get("IS_TRIGGER_ID", "")
   # .../projects/<projectId>/scripts/<pasta>/main.py
   project_id = Path(__file__).resolve().parents[2].name
   # INSERT INTO apps.<plugin_id>_run (run_id, project_id, started_at) VALUES (...)
   ```

   Gravar só quando o script pega a primeira tarefa não basta. Uma rodada que passa minutos ou
   horas listando a fonte antes de baixar algo não deixaria rastro, e o app diria "parado" com ela
   rodando.

2. **O backend do app lê o run mais recente da tabela e pergunta à porta**
   (`GET /projects/{projectId}/runs/{run_id}`). O `done` diz se está rodando, e o `result` diz como
   terminou. É a mesma chamada da espera acima. O `projectId` da rota sai da própria linha gravada.

O que a porta **não** mostra, e por quê:

| Rodada | A porta mostra? | Motivo |
|---|---|---|
| Iniciada pelo app (`POST .../runs`) | sim | workflow liberado |
| Agendamento ou tela Schedules do workflow liberado | sim | o registro guarda o slug do workflow |
| `runworkflow` do workflow liberado | sim | idem |
| Script rodado direto no Skills Lab (botão play, `skillslab -r`) | **não**: `403` ou `404` | não é rodada de workflow. O registro guarda o caminho do script no lugar do slug, e nenhuma liberação cobre isso |

Por isso, o script que o app acompanha roda **sempre por um workflow** (agendado, pela tela ou
pelo app), nunca direto pelo Skills Lab. Quando a porta não reconhece o run gravado, o app mostra
"iniciado fora do workflow" em vez de "parado", porque ele não sabe o estado.

Não crie rota de listagem nem copie o estado da rodada para uma tabela do app (heartbeat): o
estado vivo está no registro da rodada do IS, que já fecha como `INTERRUPTED` quando o back
reinicia ou alguém para a rodada.

### Parar

```java
boolean stopped = client.stopRun(projectId, triggerId);   // false: já tinha terminado
```

A rodada fecha com `result: INTERRUPTED`. O app só para rodadas de workflows liberados para ele.

---

## 7. Referência da porta

Base: `${IS_HOST_BASE_URL}/api/extensions/internal/workflows`. Todas as chamadas levam
`X-IS-Plugin-Id` e `X-IS-Plugin-Internal-Token`.

| Método | Rota | Corpo / query | Resposta |
|---|---|---|---|
| `GET` | `/projects/{projectId}/workflows` | — | `200 {"workflows": [{projectId, workflow, exists, name, workflowType}]}` — só os liberados |
| `POST` | `/projects/{projectId}/workflows/{workflow}/runs` | `{"params": {...}, "onBehalfOf": "<userId>"}`, ambos opcionais | `202 {"triggerId", "projectId", "workflow"}` |
| `GET` | `/projects/{projectId}/runs/{triggerId}` | — | `200` com `done`, `result`, `status`, `started_at`, `elapsed_ms`, `workflow_run`, `app_run`, `resources`, `exit_cause`, `peak_rss_mb` |
| `GET` | `/projects/{projectId}/runs/{triggerId}/output` | `?from=0&max=65536` (`max` até 262144) | `200 {"exists", "content", "from", "next", "more", "size", "running"}` |
| `POST` | `/projects/{projectId}/runs/{triggerId}/stop` | — | `200 {"stopped": true}` ou `409 {"stopped": false}` se já terminou |

`app_run` no registro da rodada: `{"startedBy": "app:<plugin_id>", "onBehalfOf": ..., "params": {...}}`.

Regras dos `params`:

- objeto JSON; tipos preservados (número, booleano, lista, objeto);
- até **64 KB** serializado — para dado grande, mande uma referência (nome de tabela, caminho de
  arquivo no lake), não o dado;
- não pode conter `._` seguido de um id (`"._bloco-1"`): o motor de workflow leria aquilo como
  referência a um bloco. A recusa é `400`.

---

## 8. Erros e o que cada um quer dizer

| Status | Causa | O que fazer |
|---|---|---|
| `403 Invalid internal plugin authentication` | token ou `plugin_id` errados; o token muda a cada partida do app | ler sempre de `IS_PLUGIN_INTERNAL_TOKEN`, nunca fixar |
| `403 ... is not granted to app ...` | o par `projectId`+`workflow` não está no `<plugin_id>-workflows.json` | pedir ao operador a liberação (seção 4) |
| `403 Internal ports are reachable only from inside the container` | chamada não veio de `127.0.0.1` ou passou por proxy | usar `IS_HOST_BASE_URL`; nunca chamar pelo front |
| `403 PLAN_MODULE_NOT_INCLUDED` | o plano da instância não inclui Schedules (iniciar) ou Workloads (parar) | assunto comercial, não de código |
| `403 This workflow runs an agent that is not available to user ...` | o `onBehalfOf` não tem acesso ao agente que o workflow roda | o usuário precisa de acesso ao agente |
| `400` | `params` não é objeto, passou de 64 KB ou contém `._<id>`; ou `from`/`max` fora da faixa | corrigir a chamada |
| `404 Workflow not found` | liberado no arquivo, mas não existe no projeto | conferir o slug com `lsworkflows` |
| `404 Run not found` | `triggerId` desconhecido naquele projeto | conferir o `projectId` da rota |
| `404` sem corpo da porta | o back da instância é anterior ao recurso | atualizar o back |
| `409` no stop | a rodada já tinha terminado | nada a fazer |

---

## 9. Armadilhas

- **Reiniciar o back mata a rodada.** O agendamento roda dentro da JVM do back. No boot, a rodada
  órfã é fechada como interrompida e o `GET` passa a responder `done: true, result: INTERRUPTED`.
  Se o app precisa que a rodada aconteça, ele decide se reinicia.
- **Os `params` vão só para o primeiro bloco executável.** Em workflow com vários blocos `Script`,
  os outros não recebem. Os blocos seguintes recebem dados pelas referências `._` do próprio
  workflow, como sempre.
- **Segredo não vai em `params`.** Eles ficam gravados em `trigger_jobs.json`, aparecem no log do
  IS (as chaves) e na linha de comando do script. Credencial vem do bloco `Secrets` ou do `.env` do
  script (ver `HOW_SKILLS_LAB_WORKS.md` no infinitestack-infra).
- **O `202` não diz que o script vai rodar agora.** Com limites de processo ligados
  (`proclimits`), a rodada pode esperar na fila: `result: QUEUED`.
- **Rodada do Skills Lab não é rodada de workflow.** O botão play e o `skillslab -r` criam um
  registro sem slug de workflow, e a porta não o mostra (seção 6, "Rodada que o app não iniciou").
  Para o app acompanhar, rode pelo workflow.
- **Saber o estado de uma rodada que o app não iniciou** é `IS_TRIGGER_ID` gravado pelo script +
  `GET .../runs/{triggerId}`. A porta não precisa de rota de listagem.
- **Duas rodadas do mesmo workflow podem rodar ao mesmo tempo.** O host não impede. Se o script não
  aguenta concorrência, o app controla (ex.: não iniciar outra enquanto houver uma `done: false`).

---

## 10. Testar na mão

A porta só responde de dentro do contêiner do back. Para testar sem o app, pegue o token do
processo do app **em dev** (ele muda a cada partida do app):

```bash
docker exec -it <contêiner do back> bash   # ex.: infinitestack-back-dev em dev.infinitestack.ai

PID=$(pgrep -f "<plugin_id>" | head -1)
TOKEN=$(tr '\0' '\n' < /proc/$PID/environ | sed -n 's/^IS_PLUGIN_INTERNAL_TOKEN=//p')
H=(-H "X-IS-Plugin-Id: <plugin_id>" -H "X-IS-Plugin-Internal-Token: $TOKEN" -H "Content-Type: application/json")
BASE=http://127.0.0.1:8081/api/extensions/internal/workflows

curl -s "${H[@]}" $BASE/projects/<projectId>/workflows
curl -s "${H[@]}" -X POST -d '{"params":{"year":2026}}' $BASE/projects/<projectId>/workflows/<workflow>/runs
curl -s "${H[@]}" $BASE/projects/<projectId>/runs/<triggerId>
curl -s "${H[@]}" "$BASE/projects/<projectId>/runs/<triggerId>/output?from=0"
curl -s "${H[@]}" -X POST $BASE/projects/<projectId>/runs/<triggerId>/stop
```

A rodada também aparece em `iscli -c "lsruns -p <projectId>"` e o log em
`iscli -c "catrun -id <triggerId> -tail 50"`.

Ver também, no `infinitestack-infra`: `HOW_WORKFLOWS_WORK.md` (o motor de workflow e o `--context`),
`HOW_SKILLS_LAB_WORKS.md` (rodadas, `lsruns`, `stoprun`) e `AGENT_APP_DEFINITIONS.md`.
