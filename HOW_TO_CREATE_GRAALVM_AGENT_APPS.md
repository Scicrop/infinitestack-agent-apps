# Como criar um Agent App nativo (GraalVM)

Como fazer um Agent App novo que roda como **executável nativo** compilado com GraalVM, em vez de
uma JVM. O app continua sendo o Spring Boot 3.3 / Java 17 do [README.md](README.md), com o mesmo
contrato (manifest, `base_path`, templates `isp-`, datasource do host). Muda só o que vai dentro do
`.ispz` e como o host o executa.

> Requer um back do IS com a `infinitestack-back#1369`. Num back sem ela, o `plugininstall` recusa
> o pacote com `Missing required package entry: app/plugin.jar`. Para portar um app que já existe,
> veja [HOW_TO_PORT_TO_GRAALVM_AGENT_APPS.md](HOW_TO_PORT_TO_GRAALVM_AGENT_APPS.md).

---

## Índice

1. [Quando vale a pena](#1-quando-vale-a-pena)
2. [Como funciona](#2-como-funciona)
3. [Pré-requisitos na máquina de build](#3-pré-requisitos-na-máquina-de-build)
4. [Regras de código para o modo nativo](#4-regras-de-código-para-o-modo-nativo)
5. [`pom.xml`](#5-pomxml)
6. [`plugin-manifest.json`](#6-plugin-manifestjson)
7. [Script de build: `scripts/build-native.sh`](#7-script-de-build-scriptsbuild-nativesh)
8. [Testar o binário antes de instalar](#8-testar-o-binário-antes-de-instalar)
9. [Instalar no IS](#9-instalar-no-is)
10. [Erros comuns](#10-erros-comuns)
11. [Checklist](#11-checklist)

---

## 1. Quando vale a pena

O ganho é de memória e de tempo de subida. Medido com o `meu-clima-agent-app` (web + Thymeleaf +
JDBC), mesmo `-Xmx256m`:

| | JVM (`java -jar`) | Nativo |
|---|---|---|
| Subida (log do Spring) | 1,44 s | 0,083 s |
| RSS depois de 21 requisições, local | 300 MB | 133 MB |
| RSS na dev.infinitestack.ai | média de 250 MB dos 19 apps JVM | 118 MB |
| Tamanho do `.ispz` | ~23 MB | ~29 MB |

O custo fica todo no build: ~1 a 2 minutos por app e ~8 GB de RAM de pico na compilação, contra
segundos do jar. Em runtime não há custo extra; o desempenho de pico é um pouco menor que o da JVM
aquecida, o que não pesa para apps que passam o tempo esperando banco e arquivo.

Comece nativo quando o app usa só bibliotecas com bom suporte (seção 4). Fique na JVM quando ele
depende de algo que carrega código ou bibliotecas nativas em runtime.

---

## 2. Como funciona

```
máquina de quem desenvolve                          instância do IS (contêiner debian:12)
┌────────────────────────────────────┐              ┌─────────────────────────────────────────┐
│ build-native.sh                    │   .ispz      │ plugininstall                           │
│  docker GraalVM (glibc 2.34)       │ ───────────▶ │  valida ELF, arquitetura e glibc_min    │
│  mvn -Pnative native:compile       │              │  marca app/plugin como executável       │
│  → target/<plugin_id> (ELF)        │              │ sobe: app/plugin -Xmx<n>m               │
│  → app/plugin + manifest "native"  │              │        --server.port=<porta>            │
└────────────────────────────────────┘              │ proxy /api/plugins/{id}/** igual à JVM  │
                                                    └─────────────────────────────────────────┘
```

- **O IS nunca compila.** O `.ispz` chega com o binário pronto, em `app/plugin`, no lugar do
  `app/plugin.jar`.
- **O manifest diz o runtime.** Sem `runtime`, ou com `"jvm"`, é o app de sempre. Com `"native"`,
  o host executa o binário.
- **O resto é igual:** `IS_PLUGIN_*`, credenciais do banco, proxy, `runtime-health`, log em
  `var/lake/apps/<plugin_id>.log`, portas internas, `lsplugin` (que mostra a coluna RUNTIME).
- **O heap é sempre explícito.** O host passa `-Xmx`: o `resources.max_heap_mb` do manifest, senão
  o `proclimits -app-heap`, senão a mesma fatia do contêiner que um app JVM recebe.

---

## 3. Pré-requisitos na máquina de build

- **Docker.** A compilação roda na imagem `ghcr.io/graalvm/native-image-community:17` (GraalVM CE
  para JDK 17, Oracle Linux, **glibc 2.34**).
- **Maven do sistema**, como nos outros scripts deste repo. O script monta o Maven do host dentro do
  contêiner. No Ubuntu/Debian, os arquivos do pacote `maven` são links para `/usr/share/java` e
  `/etc/maven`, por isso o script monta três pastas.
- **RAM:** ~8 GB livres durante a compilação.
- `objdump` (pacote `binutils`), `zip` e `python3`.

**Por que compilar dentro do contêiner e não direto na máquina:** o binário fica ligado à glibc de
onde foi compilado. O contêiner do back do IS é `debian:12`, com **glibc 2.36**. Compilado num
Ubuntu recente (glibc 2.43, por exemplo), o binário pede funções que a 2.36 não tem e morre na
subida com `version 'GLIBC_2.38' not found`. Binário compilado contra glibc mais velha roda numa
mais nova; o contrário não. A imagem do GraalVM tem a 2.34, abaixo da 2.36.

---

## 4. Regras de código para o modo nativo

O compilador nativo trabalha em **mundo fechado**: parte do `main`, descobre todo o código
alcançável e compila só isso. O Spring Boot 3 tem um passo de AOT que, no build, resolve os beans e
gera as configurações de reflexão do próprio Spring, Thymeleaf, Jackson e driver do PostgreSQL.
Quase tudo funciona sem nada a mais, desde que o app siga estas regras:

| Faça | Evite |
|---|---|
| Só `spring-boot-starter-web`, `-thymeleaf`, `-jdbc` e o driver `postgresql` (o conjunto do `recomendador-manejo`) | Bibliotecas que carregam `.so` por JNI em runtime (ex.: `duckdb_jdbc`) |
| DTOs como `record`, recebidos e devolvidos por `@RequestBody`/`@ResponseBody` (o Spring registra a reflexão deles) | `Class.forName`, `getDeclaredMethods`, proxies dinâmicos e classes carregadas por nome |
| `ObjectMapper.readValue(json, MinhaClasse.class)` só com `@RegisterReflectionForBinding(MinhaClasse.class)` na classe que chama | Bibliotecas de terceiros muito baseadas em reflexão sem metadados para GraalVM |
| Decidir o banco por código (`switch` no `PluginDataSourceConfig`), lendo propriedades em runtime | `@Profile` e `@ConditionalOnProperty` para escolher bean pela instalação: no nativo, isso é decidido no **build** e congela |
| Arquivos em `src/main/resources/` lidos pelo classpath (templates, JSONs de regra) | Ler do classpath com caminho montado em runtime fora do que o AOT enxerga |
| `${VAR:default}` no `application.properties`: os valores continuam sendo lidos na subida | — |

Valores de propriedade (`IS_PLUGIN_BASE_PATH`, datasource, LLM ativo) continuam sendo lidos na
subida, como na JVM. O que congela no build é **qual bean existe**, não o valor que ele recebe.

Para conferir se uma biblioteca de terceiros tem suporte, procure-a no repositório de metadados do
GraalVM ([oracle/graalvm-reachability-metadata](https://github.com/oracle/graalvm-reachability-metadata)).
O `native-maven-plugin` usa esse repositório automaticamente.

---

## 5. `pom.xml`

O `spring-boot-starter-parent` 3.3 já traz o perfil `native` e gerencia a versão do plugin. Basta
declará-lo em `<build><plugins>`, ao lado do `spring-boot-maven-plugin`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

O plugin só age com `-Pnative`. O `build-all.sh` da JVM continua igual: o mesmo projeto gera o jar
e o binário.

O nome do binário sai do `artifactId`. Mantenha o `artifactId` igual ao `plugin_id`, como nos apps
deste repo; o script procura `target/<plugin_id>`.

---

## 6. `plugin-manifest.json`

O `plugin-manifest.json` do `package-layout/` fica como o de um app JVM. O script de build acrescenta
na cópia de staging:

```json
{
  "runtime": "native",
  "native": { "os": "linux", "arch": "x86_64", "glibc_min": "2.34" }
}
```

| Campo | Valor | De onde vem |
|---|---|---|
| `runtime` | `"native"` | fixo |
| `native.os` | `"linux"` | fixo |
| `native.arch` | `x86_64` ou `aarch64` | `uname -m` da máquina de build |
| `native.glibc_min` | a maior versão `GLIBC_x.y` que o binário pede | `objdump -T` no próprio binário |

O host confere tudo isso na instalação: lê a arquitetura do cabeçalho do binário (não confia só no
manifest) e compara `glibc_min` com a glibc da instância (`getconf GNU_LIBC_VERSION`).

Os demais campos seguem o README. Declare `resources.max_heap_mb`: o nativo usa bem menos heap que
a JVM, e sem ele o app recebe o padrão da instância.

---

## 7. Script de build: `scripts/build-native.sh`

Ao lado dos `step*.sh` do app. Troque só o `PLUGIN_ID`. Não mexe no build da JVM: escreve em
`build-native/` e gera o `.ispz` em `out/`. Acrescente `build-native/` ao `.gitignore` do app.

```bash
#!/usr/bin/env bash
# Builds the GraalVM native executable of the app and packages it as a native .ispz (back#1369).
# The JVM build (build-all.sh) is untouched: this script writes to build-native/ and out/.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PLUGIN_ID="meu-agent"                                          # the plugin_id of the manifest
IMAGE="${NATIVE_IMAGE:-ghcr.io/graalvm/native-image-community:17}"  # Oracle Linux, glibc 2.34
BUILD_DIR="$PLUGIN_ROOT/build-native"
STAGING_DIR="$BUILD_DIR/staging/$PLUGIN_ID"
LAYOUT_ROOT="$PLUGIN_ROOT/package-layout/$PLUGIN_ID"
OUTPUT_DIR="$PLUGIN_ROOT/out"

# 1. Compile inside the GraalVM image, so the binary links against its older glibc and runs on
#    the IS container (debian:12, glibc 2.36). Maven comes from the host: on Ubuntu/Debian its
#    files are links into /usr/share/java and /etc/maven, so the three folders are mounted.
#    Runs as the current user, so ~/.m2 and target/ stay yours.
echo "[native] Compiling with $IMAGE ..."
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp/h \
  -v "$PLUGIN_ROOT":/src -v "$HOME/.m2":/tmp/h/.m2 \
  -v /usr/share/maven:/usr/share/maven:ro -v /usr/share/java:/usr/share/java:ro -v /etc/maven:/etc/maven:ro \
  -w /src --entrypoint /usr/share/maven/bin/mvn "$IMAGE" \
  -B -q -Pnative -DskipTests -Dmaven.repo.local=/tmp/h/.m2/repository clean native:compile

BINARY="$PLUGIN_ROOT/target/$PLUGIN_ID"
[[ -x "$BINARY" ]] || { echo "[native] ERROR: $BINARY not found" >&2; exit 1; }

# 2. What the binary really needs, read from the binary itself, not assumed.
GLIBC_MIN="$(objdump -T "$BINARY" | grep -oE 'GLIBC_[0-9.]+' | sed 's/GLIBC_//' | sort -Vu | tail -n 1)"
ARCH="$(uname -m)"
echo "[native] Binary: $(du -h "$BINARY" | cut -f1), arch $ARCH, needs glibc $GLIBC_MIN"

# 3. Staging: the same layout as the JVM package, with app/plugin instead of app/plugin.jar.
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/staging" "$OUTPUT_DIR"
cp -R "$LAYOUT_ROOT" "$STAGING_DIR"
cp "$PLUGIN_ROOT"/src/main/resources/templates/isp-*.html "$STAGING_DIR/web/templates/"
rm -f "$STAGING_DIR/app/plugin.jar" "$STAGING_DIR/checksums.sha256"
cp "$BINARY" "$STAGING_DIR/app/plugin"

# 4. Manifest: runtime "native" and the target the binary was built for. VERSION_SUFFIX (e.g.
#    "-native") keeps a test package apart from the JVM one of the same version.
python3 - "$STAGING_DIR/plugin-manifest.json" "$ARCH" "$GLIBC_MIN" "${VERSION_SUFFIX:-}" <<'EOF'
import json, sys
path, arch, glibc, suffix = sys.argv[1:5]
manifest = json.load(open(path))
manifest["version"] = manifest["version"] + suffix
manifest["runtime"] = "native"
manifest["native"] = {"os": "linux", "arch": arch, "glibc_min": glibc}
json.dump(manifest, open(path, "w"), ensure_ascii=False, indent=2)
EOF

(
  cd "$STAGING_DIR"
  sha256sum app/plugin plugin-manifest.json app/launch.properties config/plugin-permissions.json \
    web/templates/isp-*.html > checksums.sha256
)

# 5. The .ispz, named after the manifest version, like step3.
VERSION="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$STAGING_DIR/plugin-manifest.json")"
ISPZ="$OUTPUT_DIR/$PLUGIN_ID-$VERSION.ispz"
rm -f "$ISPZ"
(cd "$BUILD_DIR/staging" && zip -qr "$ISPZ" "$PLUGIN_ID")
echo "[native] Package ready: $ISPZ ($(du -h "$ISPZ" | cut -f1))"
```

```bash
./scripts/build-native.sh                       # versão do manifest
VERSION_SUFFIX=-native ./scripts/build-native.sh  # 1.2.0-native, para testar ao lado da JVM
```

Saída esperada (meu-clima, ~70 s):

```
Finished generating 'meu-clima-agent-app' in 59.5s.
[native] Binary: 86M, arch x86_64, needs glibc 2.34
[native] Package ready: .../out/meu-clima-agent-app-0.4.11-native.ispz (29M)
```

O `.ispz` sai menor do que o binário (~29 MB para 86 MB) porque o zip comprime bem o executável.
Cabe com folga no limite de upload do nginx do IS (100 MB).

**Fora do Ubuntu/Debian:** se o Maven do sistema não estiver em `/usr/share/maven` com links para
`/usr/share/java` e `/etc/maven`, extraia uma distribuição do Maven numa pasta e monte-a no lugar
das três.

---

## 8. Testar o binário antes de instalar

Teste **o binário**, não só o jar: um erro do mundo fechado (uma reflexão não registrada) só
aparece no nativo. Rode-o num `debian:12`, igual ao contêiner do IS:

```bash
docker run --rm -d --name app-native -p 18091:18091 \
  -v "$PWD/target:/app:ro" debian:12 \
  /app/meu-agent -Xmx256m --server.port=18091 --spring.main.banner-mode=off

curl -s http://127.0.0.1:18091/api/plugins/meu-agent/api/runtime-health   # ok
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18091/api/plugins/meu-agent/   # 200
docker logs app-native | grep -E 'Started|ERROR'
docker exec app-native grep VmRSS /proc/1/status
docker rm -f app-native
```

- **Datasource:** sem nenhuma variável, vale o default do `application.properties`. O pool só
  conecta no primeiro uso, então a subida não precisa do banco. Não passe `SPRING_DATASOURCE_URL`
  vazia: aí o Spring não sobe ("Failed to configure a DataSource").
- Exercite também as telas e os endpoints que leem e gravam no banco. Com um Postgres na máquina,
  rode o contêiner com `--network host` e `-e SPRING_DATASOURCE_URL=jdbc:postgresql://127.0.0.1:5432/<banco>`
  (e usuário e senha), no lugar do `-p`. É nesses caminhos que aparecem as classes que o AOT não
  enxergou.

---

## 9. Instalar no IS

Igual a um app JVM:

```bash
iscli -c "plugininstall -path /opt/infinitestack/var/lake/staging/meu-agent-1.2.0.ispz"
```

```
PLUGIN INSTALL  OK
Version:         1.2.0
Runtime:         native
```

Numa instância remota, o pacote vai pelo broker e o comando por `remotecmd`:

```bash
iscli -c "migratefs -from /lake/staging/meu-agent-1.2.0.ispz -toremote -token <token>"
iscli -c 'remotecmd -token <token> -timeout 300 -cmd "migratefs -fromremote meu-agent-1.2.0.ispz -to /lake/staging -token <token>"'
iscli -c 'remotecmd -token <token> -timeout 300 -cmd "plugininstall -path /opt/infinitestack/var/lake/staging/meu-agent-1.2.0.ispz"'
```

Para conferir: `lsplugin` mostra `RUNTIME native`, e `sysres -n 200 -sort rss` mostra o processo com
`native` no rótulo e a memória real.

---

## 10. Erros comuns

| Mensagem | Causa | Correção |
|---|---|---|
| `Missing required package entry: app/plugin.jar` | o back da instância é anterior à back#1369 | atualizar o back |
| `Missing required package entry: app/plugin` | manifest com `runtime: native` sem o binário no pacote | rodar o `build-native.sh`, não o `build-all.sh` |
| `app/plugin is built for aarch64, but this instance runs on x86_64` | binário compilado em outra arquitetura | compilar numa máquina da mesma arquitetura da instância |
| `app/plugin needs glibc 2.38 or newer, and this instance has 2.36` | compilado fora do contêiner do GraalVM, numa máquina com glibc nova | compilar pelo script (seção 7) |
| `... cannot be executed ... mounted with noexec` | volume de `/opt/infinitestack/etc/extensions` montado `noexec` | remontar sem `noexec`; a instalação já desfez a versão parcial |
| `version 'GLIBC_2.xx' not found` no log do app | `glibc_min` errado no manifest | usar o valor do `objdump`, como faz o script |
| `Plugin runtime did not become responsive in time` | o app não subiu; veja `var/lake/apps/<plugin_id>.log` | quase sempre reflexão faltando ou datasource; reproduzir com a seção 8 |
| `Could not find or load main class org.codehaus.plexus.classworlds.launcher.Launcher` no build | Maven do host montado sem `/usr/share/java` | montar as três pastas do script |
| `NoSuchFileException: /usr/share/maven/bin/m2.conf` no build | falta montar `/etc/maven` | idem |

---

## 11. Checklist

- [ ] Só dependências com suporte nativo (seção 4); nenhuma JNI carregada em runtime
- [ ] Nenhum `@Profile`/`@ConditionalOnProperty` decidindo bean por instalação
- [ ] `native-maven-plugin` no `pom.xml` e `artifactId` igual ao `plugin_id`
- [ ] `scripts/build-native.sh` com o `PLUGIN_ID` certo; `build-native/` no `.gitignore`
- [ ] `resources.max_heap_mb` declarado no manifest
- [ ] Binário testado num `debian:12` (seção 8), com as telas que acessam o banco
- [ ] `native.glibc_min` ≤ 2.36 e `native.arch` igual à da instância (o script preenche)
- [ ] Os itens do checklist do [README.md](README.md) continuam valendo
