# Como portar um Agent App existente para GraalVM

Como levar um Agent App que hoje roda na JVM (`app/plugin.jar`, `java -jar`) para o modo
**executável nativo**, sem perder a volta. O passo a passo de build, o script e as regras de código
estão em [HOW_TO_CREATE_GRAALVM_AGENT_APPS.md](HOW_TO_CREATE_GRAALVM_AGENT_APPS.md); este guia cobre
o que muda quando o app já existe: avaliar se dá, adaptar, testar ao lado da versão JVM e trocar.

> Requer um back do IS com a `infinitestack-back#1369`. A versão JVM do app continua instalável e
> é o padrão: portar é **acrescentar** um modo de build, não substituir o atual.

---

## Índice

1. [Vale a pena portar este app?](#1-vale-a-pena-portar-este-app)
2. [Avaliar as dependências](#2-avaliar-as-dependências)
3. [Procurar no código o que o mundo fechado não aceita](#3-procurar-no-código-o-que-o-mundo-fechado-não-aceita)
4. [Adaptar o projeto](#4-adaptar-o-projeto)
5. [Compilar e corrigir](#5-compilar-e-corrigir)
6. [Testar o binário](#6-testar-o-binário)
7. [Instalar ao lado da versão JVM](#7-instalar-ao-lado-da-versão-jvm)
8. [Trocar e voltar](#8-trocar-e-voltar)
9. [Exemplo: meu-clima-agent-app](#9-exemplo-meu-clima-agent-app)
10. [Checklist](#10-checklist)

---

## 1. Vale a pena portar este app?

O nativo reduz memória e tempo de subida (no `meu-clima-agent-app`: 118 MB de RSS na
dev.infinitestack.ai contra a média de 250 MB dos apps JVM, e subida de 0,08 s contra 1,4 s).
Porte primeiro:

- apps que ficam instalados em muitas instâncias, onde a soma da memória pesa;
- apps simples (web + Thymeleaf + JDBC), em que o porte costuma ser só build;
- apps que ficam a maior parte do tempo parados.

Deixe para depois, ou fique na JVM:

- apps com dependências da coluna "difícil" da seção 2;
- apps que fazem processamento pesado dentro da própria JVM por muito tempo, onde o JIT aquecido
  rende mais que o código nativo.

---

## 2. Avaliar as dependências

Liste as dependências do app:

```bash
grep -oE '<artifactId>[^<]+</artifactId>' pom.xml | sed -E 's#</?artifactId>##g'
```

| Situação | Exemplos | O que esperar |
|---|---|---|
| **Fácil** | `spring-boot-starter-web`, `-thymeleaf`, `-jdbc`, `postgresql`, `jackson` | o AOT do Spring Boot gera tudo; o porte é só build |
| **Verificar** | drivers JDBC de outros bancos (`mssql-jdbc`, `ojdbc`), clientes de nuvem (`msal4j`, SDKs Azure/AWS), `json-schema-validator` | dependem de reflexão; procure a biblioteca no repositório de metadados do GraalVM ([oracle/graalvm-reachability-metadata](https://github.com/oracle/graalvm-reachability-metadata)), que o build usa sozinho. Sem metadados, há hints a escrever |
| **Difícil** | `duckdb_jdbc` e outras bibliotecas que extraem e carregam uma `.so` por JNI em runtime; bibliotecas que geram bytecode ou carregam classes por nome | exige configuração de JNI e de recursos à mão, e muitas vezes não fecha; mantenha o app na JVM |

Nos apps deste ecossistema, quase todos são "fácil". Um app com DuckDB, `mssql-jdbc` e `msal4j` é o
caso mais exigente: se ele portar, os outros portam.

---

## 3. Procurar no código o que o mundo fechado não aceita

No nativo, só existe o que o build enxergou. Procure no app:

```bash
# Reflexão e carga dinâmica
grep -rnE 'Class\.forName|getDeclared(Method|Field|Constructor)|Proxy\.newProxyInstance|ServiceLoader' src/main/java

# Bean decidido por configuração: no nativo, isso é avaliado no BUILD e congela
grep -rnE '@Profile|@ConditionalOnProperty|@ConditionalOnExpression' src/main/java

# JSON lido para classes fora de controllers (podem precisar de registro)
grep -rnE 'readValue\(|convertValue\(|treeToValue\(' src/main/java

# Configuração importada de arquivo na subida (continua funcionando, mas teste)
grep -nE 'spring.config.import' src/main/resources/application.properties
```

O que fazer com cada achado:

| Achado | Ação |
|---|---|
| `Class.forName`, `getDeclared*`, proxy | trocar por código direto; se não der, registrar com um `RuntimeHintsRegistrar` e `@ImportRuntimeHints` |
| `@Profile`/`@ConditionalOnProperty` escolhendo bean por instalação | trocar por decisão em código (um `switch` lendo a propriedade, como o `PluginDataSourceConfig`) |
| `objectMapper.readValue(..., Classe.class)` fora de `@RequestBody`/`@ResponseBody` | `@RegisterReflectionForBinding(Classe.class)` na classe que chama |
| `spring.config.import=optional:file:...` | funciona, porque valores são lidos em runtime; teste com o arquivo presente e ausente |
| Leitura de arquivo do classpath por caminho calculado | garantir que o arquivo está em `src/main/resources/` e é lido por caminho fixo, ou registrar o recurso |

DTOs usados como `@RequestBody` e retorno de `@RestController` são registrados pelo próprio Spring;
não precisam de nada.

---

## 4. Adaptar o projeto

Em branch própria (`feat/<app>-nativo`), sem mexer no build da JVM:

1. **`pom.xml`:** acrescentar o `native-maven-plugin` em `<build><plugins>` (versão gerenciada pelo
   `spring-boot-starter-parent` 3.3). Ver seção 5 do guia de criação.
2. **`artifactId` igual ao `plugin_id`**, se ainda não for: é o nome do binário.
3. **`scripts/build-native.sh`:** copiar o script da seção 7 do guia de criação e trocar o
   `PLUGIN_ID`. Ele lê o `package-layout/` e os templates como o `step2`, então não há o que
   duplicar.
4. **`.gitignore`:** acrescentar `build-native/`.
5. **Manifest:** nada a mudar no `package-layout/`. O script acrescenta `runtime` e `native` só na
   cópia de staging. Assim, `build-all.sh` continua gerando o pacote JVM, e `build-native.sh` o
   nativo, a partir dos mesmos fontes.
6. **`resources.max_heap_mb`:** se o app não declara, declare. O nativo usa bem menos heap, e sem a
   declaração ele recebe o padrão da instância, que pode ser alto.

---

## 5. Compilar e corrigir

```bash
VERSION_SUFFIX=-native ./scripts/build-native.sh
```

Se o build falhar, o `native-image` diz a classe ou o recurso. Os casos comuns:

- **Erro de inicialização de classe no build** (`Classes that should be initialized at run time got
  initialized during image building`): uma biblioteca faz trabalho em bloco `static`. Procure-a nos
  metadados do GraalVM; se não houver, registre-a para inicializar em runtime
  (`--initialize-at-run-time=<pacote>`, em `<buildArgs>` do `native-maven-plugin`).
- **Biblioteca sem metadados:** gere-os rodando o jar na JVM com o agente do GraalVM e exercitando
  o app (`java -agentlib:native-image-agent=config-output-dir=src/main/resources/META-INF/native-image/<grupo>/<artefato> -jar target/<app>.jar`),
  e revise o que ele gravou antes de commitar.

Compilar não basta: muitos problemas só aparecem quando o código roda (seção 6).

---

## 6. Testar o binário

Siga a seção 8 do guia de criação (binário num `debian:12`, `runtime-health`, tela inicial, RSS) e
acrescente o que é específico de um app que já existe:

- [ ] Todas as abas e telas da `isp-index.html`, não só a primeira.
- [ ] Todos os endpoints que leem e gravam no banco, com um Postgres de teste.
- [ ] O que o app lê de fora: mirror, storage account, lake, arquivo de instância em
      `/opt/infinitestack/etc/data/`.
- [ ] Chamadas às portas internas do host (LLM, catálogo, workflows), se o app as usa.
- [ ] Os testes do app (`mvn -q test`) continuam passando na JVM. Eles não rodam no binário; por isso
      as verificações acima são feitas à mão contra ele.
- [ ] Comparar com a versão JVM: mesma resposta nos mesmos endpoints.

Um erro típico de reflexão faltando aparece só em runtime, como `MissingReflectionRegistrationError`
ou um JSON vazio onde deveria haver campos. Corrija com a seção 3 e recompile.

---

## 7. Instalar ao lado da versão JVM

Gere o pacote com sufixo, para não colidir com a versão JVM do mesmo número:

```bash
VERSION_SUFFIX=-native ./scripts/build-native.sh   # out/<plugin_id>-1.2.0-native.ispz
iscli -c "plugininstall -path /opt/infinitestack/var/lake/staging/<plugin_id>-1.2.0-native.ispz"
```

O host sobe a **maior** versão instalada de cada app. `1.2.0-native` é considerada maior que
`1.2.0`, então, instalada, é ela que roda. Use uma instância de teste (a dev) antes de produção.

Confira:

```bash
iscli -c "lsplugin"                    # RUNTIME native na versão -native
iscli -c "sysres -n 200 -sort rss"     # o processo, com "native" no rótulo, e o RSS real
```

---

## 8. Trocar e voltar

**Voltar para a JVM** é desinstalar a versão nativa. A versão JVM, se continuou instalada, volta a
ser a maior e sobe:

```bash
iscli -c "uninstallplugin -id <plugin_id>@1.2.0-native -confirm"
```

**Adotar o nativo de vez:**

1. Publicar a próxima versão (sem sufixo) com o `build-native.sh`, seguindo o versionamento do
   [AGENTS.md](AGENTS.md): pom e os dois manifests juntos.
2. Manter o `build-all.sh` funcionando por pelo menos uma versão, como saída de emergência: se o
   nativo falhar numa instância, sobe-se a mesma versão em JVM.
3. Registrar no README do app que ele é distribuído como nativo e como gerá-lo.

---

## 9. Exemplo: meu-clima-agent-app

Primeiro app portado, usado para validar a back#1369 na dev.infinitestack.ai.

- **Dependências:** `web`, `thymeleaf`, `jdbc`, `postgresql`, todas "fácil". Nenhuma mudança de
  código foi necessária.
- **Adaptação:** só o `native-maven-plugin` no `pom.xml` e o `build-native.sh`.
- **Build:** ~70 s no total, binário de 86 MB que pede glibc 2.34, `.ispz` de 29 MB.
- **Teste local** num `debian:12`: `runtime-health` ok e tela inicial com HTTP 200; subida em
  0,083 s contra 1,44 s na JVM; RSS de 133 MB contra 300 MB, com o mesmo `-Xmx256m`.
- **Na dev:** instalado como `0.4.11-native` por `plugininstall` via `remotecmd`, com `lsplugin`
  mostrando `RUNTIME native` e 118 MB de RSS, contra a média de 250 MB dos 19 apps JVM da mesma
  instância.

---

## 10. Checklist

- [ ] Dependências avaliadas (seção 2); nenhuma "difícil", ou um plano para ela
- [ ] Varredura da seção 3 feita e cada achado resolvido
- [ ] `native-maven-plugin`, `artifactId` = `plugin_id`, `build-native.sh`, `build-native/` no `.gitignore`
- [ ] `resources.max_heap_mb` declarado
- [ ] Binário testado em `debian:12` cobrindo todas as telas e o acesso a dados (seção 6)
- [ ] Instalado como `-native` numa instância de teste, conferido com `lsplugin` e `sysres`
- [ ] Caminho de volta conhecido: desinstalar a `-native`, ou publicar em JVM
- [ ] `build-all.sh` (JVM) continua funcionando
