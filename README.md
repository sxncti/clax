# CLAX — Claude Account eXchange

Atalho para trocar rapidamente a conta padrão do Claude Code e manter até dez contas do Claude Code abertas simultaneamente. Funciona no Linux e no Windows nativo. É o irmão do [CAX](https://github.com/sxncti/cax), que faz o mesmo para o Codex.

Cada conta numerada usa um `CLAUDE_CONFIG_DIR` próprio para manter as credenciais separadas. As conversas, os checkpoints e a sua configuração (`settings.json`, `CLAUDE.md`, skills, plugins, agents, commands) ficam no diretório padrão `~/.claude`, compartilhados entre os perfis, para que `/resume` mostre as mesmas conversas em `clax 1`, `clax 2` e no Claude Code padrão.

## Instalação no Windows

Use o PowerShell ou o Prompt de Comando do Windows. Esta instalação é nativa; não precisa de WSL.

### Requisitos

- Windows com [Python 3.10 ou mais recente](https://www.python.org/downloads/windows/) instalado, incluindo o módulo Tkinter (opção padrão do instalador oficial). O comando `py` ou `python` precisa estar no `PATH`.
- [Claude Code](https://github.com/anthropics/claude-code) instalado e acessível pelo comando `claude`.
- Uma assinatura do Claude (Pro, Max, Team ou Enterprise) para cada conta.
- Git, se for clonar e atualizar o repositório pelos comandos abaixo.

Confira os pré-requisitos no PowerShell:

```powershell
py -3 --version
claude --version
py -3 -c "import tkinter"
```

Se você instalou Python sem o lançador `py`, substitua `py -3` por `python` nesses três comandos.

### Instalar

Abra o PowerShell e execute:

```powershell
git clone https://github.com/sxncti/clax.git
cd clax
.\install.ps1
```

Se o PowerShell bloquear a execução do script, rode apenas esta instalação com uma política temporária:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

Feche e abra o terminal para carregar o novo `PATH`. Confira a instalação:

```powershell
clax help
clax 1
clax rings
```

No primeiro `clax 1`, o Claude Code abre o navegador para autenticar a conta 1. Repita com `clax 2` até `clax 10` para outras contas. Os comandos da seção [Comandos](#comandos) também funcionam no Prompt de Comando.

O instalador copia os arquivos para `%LOCALAPPDATA%\Programs\CLAX`, adiciona essa pasta ao `PATH` do usuário, prepara os perfis em `%USERPROFILE%\.claude-accounts` e cria o atalho **CLAX 5h Rings** no Menu Iniciar. O estado compartilhado fica em `%USERPROFILE%\.claude`.

### Widget de rings no Windows

Abra **CLAX 5h Rings** pelo Menu Iniciar ou execute `clax rings`. O widget é uma janela flutuante, pois o Windows não tem a barra superior do GNOME. Arraste com o botão esquerdo para reposicioná-lo; clique com o botão direito para atualizar, alterar a opção de manter acima das janelas ou fechar. Passe o mouse sobre um ring para ver a conta, os limites e o reset. Também é possível atualizar com um clique duplo.

Cada ring tem doze raios, no estilo da faísca do Claude, e mostra o percentual restante das 5 horas. Verde indica 50% ou mais, amarelo indica 20% a 49% e vermelho indica menos de 20%. Se o limite semanal acabar enquanto ainda houver limite de 5 horas, o ring fica cinza. A consulta é renovada automaticamente a cada cinco minutos.

### Atualizar no Windows

Na pasta clonada, execute:

```powershell
git pull --ff-only
.\install.ps1
```

O instalador substitui os arquivos do programa e preserva os perfis, logins e conversas. Se você não tiver mais a pasta clonada, clone novamente e repita a instalação.

### Solução de problemas no Windows

- Se `clax` não for reconhecido após instalar, abra um novo terminal. Para conferir o arquivo instalado diretamente, execute `& "$env:LOCALAPPDATA\Programs\CLAX\clax.cmd" help` no PowerShell.
- Se o instalador não encontrar o Claude Code, verifique `claude --version` em um novo terminal e instale o [Claude Code](https://github.com/anthropics/claude-code) antes de repetir `install.ps1`.
- Se `clax rings` reclamar de Tkinter, instale o componente **Tcl/Tk and IDLE** do Python e confira com `py -3 -c "import tkinter"`.
- O Windows só permite symlinks de arquivo com o modo de desenvolvedor ativo. Sem ele, as pastas continuam compartilhadas (por junção), mas `settings.json`, `CLAUDE.md` e o histórico de prompts ficam separados em cada perfil.
- Se o navegador entrar na conta errada, veja a dica no fim da seção [Comandos](#comandos).

## Instalação no Linux

Requer Python 3.10 ou mais recente, [Claude Code](https://github.com/anthropics/claude-code) e uma assinatura do Claude para cada conta. Execute:

```bash
git clone https://github.com/sxncti/clax.git
cd clax
./install.sh
```

O instalador coloca o programa em `~/.local/share/clax`, cria o comando `~/.local/bin/clax`, adiciona o lançador **CLAX — Trocar conta do Claude Code** ao menu de aplicativos e prepara os perfis `1` a `10`.

No GNOME, ele também instala o indicador **CLAX 5h Rings**. Após a primeira instalação, saia e entre novamente na sessão para o GNOME reconhecer a nova extensão; então ative-a uma vez com:

```bash
gnome-extensions enable clax-rings@sxncti.github.com
```

Um ring para cada conta conectada aparece no lado direito da barra superior. As cores e o bloqueio semanal seguem as mesmas regras do widget para Windows, com atualização a cada cinco minutos ou pelo menu do indicador. Fora do GNOME, use o widget flutuante com `clax rings` (requer o pacote `python3-tk`).

Para atualizar, na pasta clonada, execute:

```bash
git pull --ff-only
./install.sh
```

O instalador substitui somente o programa, o lançador e a extensão. As contas, credenciais e conversas existentes em `~/.claude-accounts` e `~/.claude` são preservadas. Se você apagou a pasta original, clone o projeto novamente e execute `./install.sh`.

O macOS ainda não foi testado. Lá o Claude Code guarda a credencial no Keychain, então o CLAX consulta os limites pelo próprio Claude Code, o que é mais lento.

## Uso rápido

Abra contas diferentes em terminais diferentes:

```text
# Terminal 1
clax 1

# Terminal 2
clax 2

# Terminal 3
clax 3
```

No primeiro uso de cada número, o CLAX abre o navegador para autenticação. Depois disso, basta executar novamente `clax 1`, `clax 2` etc. A credencial fica armazenada no perfil correspondente e o Claude Code renova os tokens automaticamente enquanto forem válidos.

Argumentos extras vão direto para o Claude Code:

```text
clax 2 --resume
clax 3 --model opus
clax 1 -p "resuma o README"
```

Você só precisará autenticar novamente se fizer logout ou switch, revogar a sessão, ou se a credencial deixar de ser válida.

## Comandos

| Comando | Ação |
| --- | --- |
| `clax` | Faz logout da conta padrão e abre o navegador para outra conta |
| `clax 1` … `clax 10` | Abre o Claude Code com a conta numerada |
| `clax list` / `clax ls` | Lista as dez contas, seus e-mails, estados e os limites restantes de 5 horas e semanal |
| `clax bar-data` | Saída estável usada pelos indicadores de rings |
| `clax N login` | Autentica a conta `N` |
| `clax N status` | Mostra se a conta `N` está conectada |
| `clax N switch` | Faz logout e login somente na conta `N` |
| `clax N logout` | Desconecta somente a conta `N` |
| `clax help` | Mostra a ajuda no terminal |
| `clax auto "TAREFA"` | Executa uma tarefa autônoma e troca de conta se o limite acabar |
| `clax auto resume UUID` | Continua uma sessão existente com troca automática de conta |
| `clax rings` | Abre o widget flutuante de rings |
| `clax setup` | Prepara os perfis 1 a 10 (o instalador já executa) |

O login usa a sessão do Claude que estiver aberta no navegador. Se o navegador insistir em usar a conta errada, copie o endereço exibido pelo `clax N login` e abra-o em uma janela anônima, ou preencha o e-mail da conta desejada:

```text
clax 2 login --email outra@exemplo.com
```

O `clax list` mostra a parte anterior ao `@` do e-mail associado a cada login. Os limites são os mesmos mostrados pelo `/usage` do Claude Code, e cada percentual vem acompanhado de uma pilha visual com cinco segmentos e do tempo restante até o reset, como `70% [■■■■□] (2h14m)`. A consulta não envia uma mensagem nem consome o limite. Se o serviço estiver temporariamente inacessível, o CLAX mostra `indisp.` sem considerar a conta desconectada.

Em terminais compatíveis, o CLAX colore somente a contagem regressiva para destacar a proximidade do reset. Defina `NO_COLOR=1` ou `CLAX_COLOR=never` para desativar as cores; use `CLAX_COLOR=always` para mantê-las mesmo quando a saída for redirecionada.

## Continuação automática

Para uma tarefa autônoma longa, use, dentro da pasta do projeto:

```text
clax auto "implemente a tarefa, execute os testes e corrija eventuais falhas"
```

O CLAX escolhe a conta conectada com a melhor combinação de limite de 5 horas e semanal. Se o Claude Code encerrar o turno por falta de limite, o CLAX preserva o UUID da sessão, escolhe outra conta com limite e continua o mesmo trabalho automaticamente. Como as conversas ficam no diretório compartilhado, a nova conta retoma exatamente a mesma sessão.

Também é possível assumir uma sessão já existente:

```text
clax auto resume 00000000-0000-0000-0000-000000000000
```

Execute `clax auto resume` na mesma pasta em que a sessão foi criada, pois o Claude Code organiza as conversas por projeto. O UUID aparece no início da execução (`session id: ...`) e no `/resume` do Claude Code.

O modo `auto` usa a execução não interativa do Claude Code (`claude -p`) com o modo de permissão `auto`, em que um classificador aprova as ações seguras e bloqueia as arriscadas, sem pausa para aprovação manual. Para mudar, defina `CLAX_AUTO_PERMISSION_MODE` com outro modo do Claude Code, como `acceptEdits` ou `bypassPermissions`. O CLAX troca de conta somente quando o Claude Code informa que o limite da conta acabou; outros erros são devolvidos normalmente. Use apenas contas que você está autorizado a acessar e respeite os termos do seu plano.

## Como funciona

Os perfis ficam separados em `~/.claude-accounts` no Linux ou `%USERPROFILE%\.claude-accounts` no Windows:

```text
~/.claude-accounts/
├── 1/
├── 2/
├── 3/
├── ...
└── 10/
```

O CLAX define `CLAUDE_CONFIG_DIR` para o diretório da conta selecionada. Assim, cada perfil mantém seu próprio `.credentials.json` e seu próprio `.claude.json`, onde o Claude Code guarda a conta conectada.

Ao preparar um perfil, o CLAX cria links para o estado compartilhado em `~/.claude`:

| Compartilhado | Separado por conta |
| --- | --- |
| `projects/` (conversas do `/resume` e memória dos projetos), `file-history/`, `todos/`, `plans/` | `.credentials.json` |
| `agents/`, `commands/`, `skills/`, `plugins/`, `output-styles/`, `hooks/`, quando existirem | `.claude.json` |
| `settings.json`, `CLAUDE.md`, `keybindings.json`, `history.jsonl`, quando existirem | logins de servidores MCP |

Se um desses itens já existir de verdade dentro do perfil, o CLAX não mexe nele. Os links de arquivo são o melhor esforço: se o Claude Code regravar um deles substituindo o arquivo, aquele perfil passa a ter uma cópia própria. Um perfil novo também recebe do seu `~/.claude.json` apenas as preferências de onboarding, tema, modo do editor e servidores MCP do usuário, para não repetir a configuração inicial; nada da conta padrão é copiado.

Para mostrar os limites, o CLAX lê o token do perfil e consulta o mesmo serviço usado pelo `/usage`. Se o token salvo já tiver expirado, o CLAX roda `claude -p /usage` no perfil: é um comando local que não envia mensagem nem consome limite, e faz o próprio Claude Code renovar o token. Esse caminho mais lento também executa os hooks `SessionStart` que você tiver configurado.

Para usar outro local para o estado compartilhado, defina `CLAX_SHARED_STATE_HOME`:

```bash
CLAX_SHARED_STATE_HOME=/outro/diretorio clax 2
```

No PowerShell, defina a variável antes de executar o CLAX:

```powershell
$env:CLAX_SHARED_STATE_HOME = 'D:\Claude\estado'
clax 2
```

O mesmo padrão vale para `CLAX_PROFILES_HOME`, que muda o local dos perfis, e para `CLAUDE_COMMAND`, que aponta para outro executável do Claude Code. Se você usar esses caminhos personalizados, configure as variáveis também nas sessões futuras do terminal e antes de executar o instalador.

Dentro de uma sessão aberta pelo CLAX, a variável `CLAX_PROFILE` informa o número da conta, o que é útil em uma statusline. Se `ANTHROPIC_API_KEY` estiver definida no ambiente, o Claude Code usa essa chave no lugar do login de cada perfil.

## Segurança

Os arquivos `.credentials.json` contêm tokens de acesso. No Linux, o CLAX cria os diretórios dos perfis com permissão `700`; no Windows, os arquivos ficam no perfil do usuário. Em ambos os casos, trate-os como senhas:

- não envie `~/.claude-accounts` para o Git;
- não compartilhe os arquivos `.credentials.json`;
- não cole o conteúdo deles em chats ou chamados de suporte.

Este repositório não contém credenciais.

## Remoção no Linux

Remova o programa, o comando, o lançador e a extensão:

```bash
rm -r ~/.local/share/clax
rm ~/.local/bin/clax
rm ~/.local/share/applications/clax.desktop
rm -r ~/.local/share/gnome-shell/extensions/clax-rings@sxncti.github.com
```

Os perfis e logins permanecem em `~/.claude-accounts`. Apague esse diretório somente se também quiser remover todas as credenciais das contas; `rm -r ~/.claude-accounts` remove apenas os links, sem entrar em `~/.claude`. As conversas ficam no estado compartilhado padrão e não são apagadas junto com os perfis.

## Remoção no Windows

Feche o widget, exclua `%LOCALAPPDATA%\Programs\CLAX` e o atalho **CLAX 5h Rings** do Menu Iniciar. Remova também a entrada da pasta CLAX do `PATH` do usuário nas configurações de variáveis de ambiente do Windows. Os perfis em `%USERPROFILE%\.claude-accounts` e o estado compartilhado em `%USERPROFILE%\.claude` permanecem disponíveis; remova-os separadamente somente se quiser apagar credenciais e conversas.

Os perfis contêm junções que apontam para `%USERPROFILE%\.claude`. Para apagá-los, use `cmd /c rmdir /s /q "%USERPROFILE%\.claude-accounts"`, que remove as junções sem entrar nelas. Evite `Remove-Item -Recurse` no Windows PowerShell 5.1, que pode seguir as junções e apagar o conteúdo compartilhado.
