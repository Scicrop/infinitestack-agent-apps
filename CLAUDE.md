# CLAUDE.md

As instruções do projeto ficam em [AGENTS.md](AGENTS.md), compartilhadas com outros agentes. Elas são importadas abaixo.

@AGENTS.md

## Específico do Claude Code

- Antes de criar tabela, controller ou template, leia a seção correspondente do
  [README.md](README.md). Antes de mexer em UI, leia o [design.md](design.md).
- Para validar uma mudança de UI no app rodando, suba o app localmente com
  `mvn spring-boot:run` dentro do diretório do app. Ele usa os defaults `${VAR:default}` do
  `application.properties`, que exigem um Postgres local. Abra `http://localhost:8080{base_path}/`.
- Modo claro: o tema escuro é o padrão, e o modo claro é uma opção de quem usa, por um botão no
  header. Para criar ou mexer nele, siga a seção "Modo claro e escuro" do [README.md](README.md):
  cores só em variáveis CSS (`:root` escuro, `:root[data-theme="light"]` claro), escolha salva no
  `localStorage` e aplicada no `<head>` antes do primeiro desenho, e gráficos em canvas e SVG
  desenhado por JS lendo as variáveis. Valide as telas nos dois modos.
- Não faça commit, push nem bump de versão sem pedido explícito.
