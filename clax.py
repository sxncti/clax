#!/usr/bin/env python3
"""CLAX = Claude Account eXchange. Usa somente a biblioteca padrao do Python.

Sem argumentos, troca a conta padrao. Com 1 a 10, abre uma conta isolada.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta


VERSION = "1.0.0"
PROFILE_NUMBERS = range(1, 11)
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CONTINUATION = "Continue a tarefa exatamente de onde parou. Verifique o estado atual dos arquivos antes de prosseguir."
# Inicios das mensagens que o Claude Code mostra quando o limite da conta acaba.
LIMIT_PREFIXES = ("You've hit your", "You've reached your", "You're out of usage credits",
                  "Claude AI usage limit reached", "Usage limit reached")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SESSION_LINE = re.compile(r"^Current session:\s*(\d+)% used(?:\s*\S\s*resets\s+(.+))?$", re.M)
WEEK_LINE = re.compile(r"^Current week \(all models\):\s*(\d+)% used(?:\s*\S\s*resets\s+(.+))?$", re.M)
RESET_TEXT = re.compile(r"^(?:(?P<month>[A-Za-z]{3})\w*\s+(?P<day>\d{1,2}),?\s+)?"
                        r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)", re.I)
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")

# Estado compartilhado entre as contas: conversas (/resume), checkpoints e configuracao.
SHARED_STATE_DIRS = ("projects", "file-history", "todos", "plans")
SHARED_CONFIG_DIRS = ("agents", "commands", "skills", "plugins", "output-styles", "hooks")
SHARED_FILES = ("settings.json", "CLAUDE.md", "keybindings.json", "history.jsonl")
# Preferencias copiadas do .claude.json padrao para pular o onboarding nos perfis novos.
SEEDED_KEYS = ("hasCompletedOnboarding", "lastOnboardingVersion", "theme", "editorMode", "mcpServers")


@dataclass
class Usage:
    email: str = "--"
    five: int | None = None
    five_reset: int | None = None
    week: int | None = None
    week_reset: int | None = None


def pause_launcher() -> None:
    if os.environ.get("CLAX_LAUNCHER") == "1" and sys.stdin.isatty():
        try:
            input("\nPressione Enter para fechar...")
        except EOFError:
            pass


def fail(message: str, code: int = 1) -> None:
    print(f"Erro: {message}", file=sys.stderr)
    pause_launcher()
    raise SystemExit(code)


def find_claude() -> str | None:
    """Procura o Claude Code tambem fora do PATH, como acontece na extensao do GNOME."""
    command = os.environ.get("CLAUDE_COMMAND", "claude")
    found = shutil.which(command)
    if found:
        return found
    home = Path.home()
    for candidate in (home / ".local" / "bin" / "claude", home / ".claude" / "local" / "claude",
                      home / ".npm-global" / "bin" / "claude"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def claude_command() -> str:
    found = find_claude()
    if not found:
        fail("o comando claude nao foi encontrado. Instale o Claude Code.", 127)
    return found


def is_inside(path: Path, root: Path) -> bool:
    path, root = path.expanduser().resolve(), root.expanduser().resolve()
    return path == root or root in path.parents


def roots() -> tuple[Path, Path]:
    home = Path.home()
    profiles = Path(os.environ.get("CLAX_PROFILES_HOME") or home / ".claude-accounts")
    shared = os.environ.get("CLAX_SHARED_STATE_HOME")
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    # Dentro de uma sessao do CLAX, CLAUDE_CONFIG_DIR aponta para o perfil e nao serve de base.
    if not shared and configured and not is_inside(Path(configured), profiles):
        shared = configured
    return profiles, Path(shared or home / ".claude")


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    configured = env.get("CLAUDE_CONFIG_DIR")
    if configured and is_inside(Path(configured), roots()[0]):
        env.pop("CLAUDE_CONFIG_DIR")
    env.pop("CLAX_PROFILE", None)
    return env


def profile_env(profile: Path) -> dict[str, str]:
    env = base_env()
    env["CLAUDE_CONFIG_DIR"] = str(profile)
    env["CLAX_PROFILE"] = profile.name
    return env


def link_entry(link: Path, target: Path, directory: bool) -> None:
    if link.exists() or link.is_symlink():
        return
    try:
        if directory and os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=directory)
    except (OSError, ImportError, AttributeError):
        pass  # No Windows sem modo de desenvolvedor, arquivos nao podem virar symlink.


def link_shared_state(profile: Path, shared: Path) -> None:
    for name in SHARED_STATE_DIRS:
        target = shared / name
        target.mkdir(parents=True, exist_ok=True)
        link_entry(profile / name, target, True)
    for name in SHARED_CONFIG_DIRS:
        if (shared / name).is_dir():
            link_entry(profile / name, shared / name, True)
    for name in SHARED_FILES:
        if (shared / name).is_file():
            link_entry(profile / name, shared / name, False)


def seed_claude_json(profile: Path, shared: Path) -> None:
    target = profile / ".claude.json"
    if target.exists():
        return
    for source in (shared / ".claude.json", Path.home() / ".claude.json"):
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        seed = {key: data[key] for key in SEEDED_KEYS if isinstance(data, dict) and key in data}
        if seed:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(seed, handle, indent=2)
        return


def prepare_profile(number: int) -> Path:
    profiles, shared = roots()
    profile = profiles / str(number)
    try:
        profile.mkdir(mode=0o700, parents=True, exist_ok=True)
        shared.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(profiles, 0o700)
            os.chmod(profile, 0o700)
        link_shared_state(profile, shared)
        seed_claude_json(profile, shared)
    except OSError as exc:
        fail(f"nao foi possivel preparar o perfil {number}: {exc}")
    return profile


def run_claude(command: str, profile: Path, *args: str, quiet: bool = False) -> int:
    try:
        result = subprocess.run([command, *args], env=profile_env(profile),
                                stdout=subprocess.DEVNULL if quiet else None,
                                stderr=subprocess.DEVNULL if quiet else None)
        return result.returncode
    except OSError as exc:
        fail(f"nao foi possivel executar o Claude Code: {exc}")


def credentials(profile: Path) -> dict:
    try:
        data = json.loads((profile / ".credentials.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    oauth = data.get("claudeAiOauth") if isinstance(data, dict) else None
    return oauth if isinstance(oauth, dict) else {}


def logged_in(command: str | None, profile: Path) -> bool:
    if credentials(profile).get("accessToken"):
        return True
    # No macOS a credencial fica no Keychain; pergunta ao proprio Claude Code.
    if sys.platform == "darwin" and command:
        return run_claude(command, profile, "auth", "status", quiet=True) == 0
    return False


def account_email(profile: Path) -> str:
    try:
        data = json.loads((profile / ".claude.json").read_text(encoding="utf-8"))
        email = data["oauthAccount"]["emailAddress"]
    except (OSError, ValueError, KeyError, TypeError):
        return "--"
    if not isinstance(email, str) or not email:
        return "--"
    return re.sub(r"\s+", " ", email.split("@")[0]).strip() or "--"


def iso_epoch(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    # Remove a fracao de segundo: o Python 3.10 so aceita 3 ou 6 digitos.
    cleaned = re.sub(r"\.\d+", "", value.strip()).replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(cleaned).timestamp())
    except ValueError:
        return None


def remaining(used: object) -> int | None:
    if isinstance(used, bool) or not isinstance(used, (int, float)):
        return None
    return max(0, min(100, 100 - round(used)))


def usage_api(token: str) -> dict | None:
    request = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Accept": "application/json",
        "User-Agent": f"clax/{VERSION}",
    })
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def usage_from_api(data: dict, email: str) -> Usage | None:
    result = Usage(email=email)
    five = data.get("five_hour") if isinstance(data.get("five_hour"), dict) else {}
    week = data.get("seven_day") if isinstance(data.get("seven_day"), dict) else {}
    result.five, result.five_reset = remaining(five.get("utilization")), iso_epoch(five.get("resets_at"))
    result.week, result.week_reset = remaining(week.get("utilization")), iso_epoch(week.get("resets_at"))
    return result if result.five is not None or result.week is not None else None


def reset_epoch(text: str | None, now: datetime | None = None) -> int | None:
    """Converte resets como 'Oct 3, 12:30pm (America/Sao_Paulo)' no horario local."""
    match = RESET_TEXT.match(text.strip()) if text else None
    if not match:
        return None
    now = now or datetime.now()
    hour = int(match["hour"]) % 12 + (12 if match["ampm"].lower() == "pm" else 0)
    minute = int(match["minute"] or 0)
    try:
        if match["month"]:
            month = MONTHS.index(match["month"].lower()) + 1
            moment = now.replace(month=month, day=int(match["day"]), hour=hour, minute=minute,
                                 second=0, microsecond=0)
            if moment < now - timedelta(days=1):
                moment = moment.replace(year=now.year + 1)
        else:
            moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if moment < now:
                moment += timedelta(days=1)
    except ValueError:
        return None
    return int(moment.timestamp())


def usage_from_text(text: str, email: str) -> Usage | None:
    """Le a saida de /usage, usada quando a API nao aceita o token salvo."""
    result = Usage(email=email)
    session = SESSION_LINE.search(text)
    week = WEEK_LINE.search(text)
    if session:
        result.five, result.five_reset = remaining(int(session[1])), reset_epoch(session[2])
    if week:
        result.week, result.week_reset = remaining(int(week[1])), reset_epoch(week[2])
    return result if session or week else None


def usage_via_cli(command: str | None, profile: Path) -> str | None:
    """Roda /usage como comando local: nao envia mensagem e renova o token se preciso."""
    if not command:
        return None
    try:
        completed = subprocess.run(
            [command, "-p", "/usage", "--output-format", "json", "--no-session-persistence"],
            env=profile_env(profile), cwd=profile, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        data = json.loads(completed.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None
    if isinstance(data, dict) and data.get("local_command") == "usage" and isinstance(data.get("result"), str):
        return data["result"]
    return None


def usage_limits(command: str | None, profile: Path) -> Usage | None:
    email = account_email(profile)
    oauth = credentials(profile)
    token = oauth.get("accessToken")
    expires = oauth.get("expiresAt")
    fresh = not isinstance(expires, (int, float)) or expires / 1000 > time.time() + 60
    data = usage_api(token) if token and fresh else None
    if data is None:
        text = usage_via_cli(command, profile)
        renewed = credentials(profile).get("accessToken")
        if renewed and renewed != token:
            data = usage_api(renewed)
        if data is None:
            return usage_from_text(text, email) if text else None
    return usage_from_api(data, email)


def collect_profiles(command: str | None) -> list[tuple[int, bool, Usage | None]]:
    profiles = roots()[0]
    if not profiles.is_dir():
        return []
    existing = [(n, profiles / str(n)) for n in PROFILE_NUMBERS if (profiles / str(n)).is_dir()]
    if not existing:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        status_futures = {n: pool.submit(logged_in, command, path) for n, path in existing}
        usage_futures = {n: pool.submit(usage_limits, command, path) for n, path in existing
                         if status_futures[n].result()}
        return [(n, status_futures[n].result(),
                 usage_futures[n].result() if n in usage_futures else None)
                for n, _ in existing]


def reset_time(epoch: int | None) -> str:
    if epoch is None:
        return "--"
    minutes = max(0, (epoch - int(time.time()) + 59) // 60)
    if not minutes:
        return "agora"
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{mins:02d}m"
    return f"{mins}m"


def field(percent: int | None, reset: int | None, connected: bool) -> str:
    if percent is None:
        return "indisp." if connected else "--"
    filled = min(5, (percent + 19) // 20)
    return f"{percent}% [{'■' * filled}{'□' * (5 - filled)}] ({reset_time(reset)})"


def colored_field(plain: str, reset: int | None, window: int) -> str:
    padded = f"{plain:<25}"
    mode = os.environ.get("CLAX_COLOR", "auto")
    if reset is None or mode == "never" or (mode != "always" and
            (not sys.stdout.isatty() or os.environ.get("NO_COLOR"))):
        return padded
    seconds = max(0, reset - int(time.time()))
    green, yellow = (3600, 10800) if window == 300 else (86400, 259200)
    color = "32" if seconds <= green else "33" if seconds <= yellow else "31"
    countdown = f"({reset_time(reset)})"
    return padded.replace(countdown, f"\033[{color}m{countdown}\033[0m", 1)


def list_profiles(command: str | None) -> None:
    rows = collect_profiles(command)
    if not rows and not roots()[0].is_dir():
        print("As contas ainda nao foram criadas.")
        return
    emails = {number: account_email(roots()[0] / str(number)) for number, _, _ in rows}
    width = max([12, *(len(email) for email in emails.values())])
    print(f"{'conta':<6} {'email':<{width}} {'status':<12} {'5h restante':<25} {'semana restante':<25}")
    for number, connected, usage in rows:
        email = usage.email if usage else emails[number] if connected else "--"
        five = field(usage.five if usage else None, usage.five_reset if usage else None, connected)
        week = field(usage.week if usage else None, usage.week_reset if usage else None, connected)
        five_display = colored_field(five, usage.five_reset if usage else None, 300)
        week_display = colored_field(week, usage.week_reset if usage else None, 10080)
        print(f"{number:<6} {email:<{width}} {'conectado' if connected else 'desconectado':<12} {five_display} {week_display}")


def bar_data(command: str | None) -> None:
    for number, connected, usage in collect_profiles(command):
        if connected and usage and usage.five is not None:
            email = usage.email.replace("\t", " ")
            weekly = usage.week if usage.week is not None else -1
            # Formato estavel: conta, email, 5h restante, reset de 5h e semana restante.
            print(f"{number}\t{email}\t{usage.five}\t{reset_time(usage.five_reset)}\t{weekly}")


def is_limit_message(text: object) -> bool:
    return isinstance(text, str) and text.strip().startswith(LIMIT_PREFIXES)


def tool_summary(name: str, data: object) -> str:
    detail = ""
    if isinstance(data, dict):
        for key in ("command", "file_path", "path", "pattern", "url", "query", "description", "prompt"):
            if isinstance(data.get(key), str) and data[key].strip():
                detail = " ".join(data[key].split())
                break
    if len(detail) > 100:
        detail = detail[:97] + "..."
    return f"→ {name}: {detail}" if detail else f"→ {name}"


def render_event(event: object) -> str | None:
    """Mostra um evento do stream-json e devolve 'limit', 'rejected' ou 'error' quando relevante."""
    if not isinstance(event, dict):
        return None
    kind = event.get("type")
    if kind == "system" and event.get("subtype") == "init":
        print(f"session id: {event.get('session_id', '--')} · modelo {event.get('model', '--')}", flush=True)
    elif kind == "rate_limit_event":
        info = event.get("rate_limit_info") if isinstance(event.get("rate_limit_info"), dict) else {}
        if info.get("status") == "rejected" and not info.get("isUsingOverage"):
            return "rejected"
    elif kind == "assistant":
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        signal = None
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and str(block.get("text", "")).strip():
                print(str(block["text"]).strip(), flush=True)
                if event.get("error") and is_limit_message(block["text"]):
                    signal = "limit"
            elif block.get("type") == "tool_use":
                print(tool_summary(str(block.get("name", "ferramenta")), block.get("input")), flush=True)
        return signal
    elif kind == "result" and event.get("is_error"):
        errors = event.get("errors") if isinstance(event.get("errors"), list) else []
        texts = [text for text in (event.get("result"), *errors) if isinstance(text, str) and text.strip()]
        print("\n" + ("\n".join(texts) or str(event.get("subtype") or "erro")), file=sys.stderr, flush=True)
        return "limit" if any(is_limit_message(text) for text in texts) else "error"
    return None


def auto_mode(command: str, args: list[str]) -> int:
    resuming = False
    if args and args[0] == "resume":
        if len(args) < 2 or not UUID.fullmatch(args[1]):
            fail("informe o UUID da sessao: clax auto resume UUID")
        session_id, resuming = args[1], True
        prompt = " ".join(args[2:]) or CONTINUATION
    else:
        if not args:
            fail('informe a tarefa: clax auto "sua tarefa"')
        session_id, prompt = str(uuid.uuid4()), " ".join(args)
    permission_mode = os.environ.get("CLAX_AUTO_PERMISSION_MODE", "auto")
    tried: set[int] = set()
    while True:
        eligible = [(n, u) for n, connected, u in collect_profiles(command)
                    if n not in tried and connected and u and u.five and u.week]
        if not eligible:
            print("Nenhuma outra conta conectada possui limite de 5h e semanal disponivel.", file=sys.stderr)
            print(f"Sessao preservada: {session_id}", file=sys.stderr)
            return 1
        number, usage = max(eligible, key=lambda item:
                            (min(item[1].five or 0, item[1].week or 0), item[1].five or 0, item[1].week or 0))
        profile = prepare_profile(number)
        print(f"\nCLAX auto: conta {number} ({usage.email}), 5h {usage.five}%, semana {usage.week}%.\n", flush=True)
        invocation = [command, "-p", "--output-format", "stream-json", "--verbose",
                      "--permission-mode", permission_mode]
        invocation += ["--resume", session_id] if resuming else ["--session-id", session_id]
        proc = None
        try:
            # O prompt vai pela entrada padrao para nunca ser confundido com uma opcao.
            proc = subprocess.Popen(invocation, env=profile_env(profile), stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", bufsize=1)
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
            signals: set[str] = set()
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    print(line, end="", flush=True)
                    continue
                signals.add(render_event(event) or "")
            status = proc.wait()
            # Uma rejeicao so conta se o turno falhou; o Claude Code pode seguir em outro modelo.
            limit_found = "limit" in signals or {"rejected", "error"} <= signals
        except KeyboardInterrupt:
            if proc:
                proc.terminate()
                proc.wait()
            print(f"\nSessao preservada: {session_id}", file=sys.stderr)
            return 130
        except OSError as exc:
            fail(f"nao foi possivel executar o Claude Code: {exc}")
        resuming = True
        if limit_found:
            tried.add(number)
            prompt = CONTINUATION
            print(f"\nCLAX auto: limite da conta {number} esgotado; procurando outra conta...", flush=True)
            continue
        if status:
            print(f"Sessao: {session_id}", file=sys.stderr)
        return status


def launch(command: str, profile: Path, args: list[str]) -> int:
    argv = [command, *args]
    if os.name == "posix":
        sys.stdout.flush()
        sys.stderr.flush()
        try:
            os.execve(command, argv, profile_env(profile))
        except OSError as exc:
            fail(f"nao foi possivel executar o Claude Code: {exc}")
    return run_claude(command, profile, *args)


def switch_default(command: str) -> int:
    env = base_env()
    print("Trocando a conta padrao do Claude Code...", flush=True)
    if subprocess.run([command, "auth", "status"], env=env, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0:
        if subprocess.run([command, "auth", "logout"], env=env).returncode:
            fail("nao foi possivel remover a sessao atual.")
    print("\nAbrindo o navegador para entrar em outra conta...", flush=True)
    if subprocess.run([command, "auth", "login"], env=env).returncode:
        fail("o login nao foi concluido. Rode clax para tentar novamente.")
    print("\nPronto: a nova conta esta conectada ao Claude Code.")
    return 0


def usage() -> None:
    print("""CLAX — Claude Account eXchange

Uso:
  clax                        troca a conta padrao do Claude Code
  clax NUMERO                 abre a conta isolada (1 a 10)
  clax NUMERO login           entra ou troca essa conta
  clax NUMERO logout          sai somente dessa conta
  clax NUMERO status          mostra se a conta esta conectada
  clax NUMERO switch          logout + login somente nessa conta
  clax list / clax ls         lista as contas e os limites restantes
  clax bar-data               fornece os limites para os rings
  clax auto "TAREFA"          executa com troca automatica de conta
  clax auto resume UUID       continua uma sessao com troca automatica
  clax rings                  abre o widget flutuante de rings
  clax setup                  prepara os perfis 1 a 10

Exemplo simultaneo, em dois terminais:
  clax 1
  clax 2

Argumentos extras vao direto para o Claude Code:
  clax 2 --resume
  clax 3 --model opus""")


def main(args: list[str]) -> int:
    if args and args[0] in ("-h", "--help", "help"):
        usage()
        return 0
    if args and args[0] in ("-V", "--version", "version"):
        print(f"clax {VERSION}")
        return 0
    if args and args[0] == "rings":
        try:
            from clax_rings import main as rings_main
        except ImportError as exc:
            if exc.name not in ("tkinter", "_tkinter"):
                raise
            fail("o widget requer Tkinter. No Linux, instale o pacote python3-tk.")
        return rings_main()
    if args and args[0] in ("list", "ls"):
        list_profiles(find_claude())
        return 0
    if args and args[0] == "bar-data":
        bar_data(find_claude())
        return 0
    if args and args[0] == "setup":
        for number in PROFILE_NUMBERS:
            prepare_profile(number)
        print(f"Perfis 1 a 10 prontos em {roots()[0]}.")
        return 0
    command = claude_command()
    if not args:
        return switch_default(command)
    if args[0] == "auto":
        return auto_mode(command, args[1:])
    if not re.fullmatch(r"(?:[1-9]|10)", args[0]):
        fail("conta invalida. Use um numero de 1 a 10.")
    number = int(args[0])
    profile = prepare_profile(number)
    rest = args[1:]
    if rest and rest[0] == "login":
        return run_claude(command, profile, "auth", "login", *rest[1:])
    if rest and rest[0] == "logout":
        return run_claude(command, profile, "auth", "logout", *rest[1:])
    if rest and rest[0] == "status":
        return run_claude(command, profile, "auth", "status", *(rest[1:] or ["--text"]))
    if rest and rest[0] == "switch":
        if logged_in(command, profile):
            status = run_claude(command, profile, "auth", "logout")
            if status:
                return status
        return run_claude(command, profile, "auth", "login", *rest[1:])
    if not logged_in(command, profile):
        print(f'Primeiro acesso ao perfil "{number}". Abrindo o login no navegador...\n', flush=True)
        if run_claude(command, profile, "auth", "login"):
            fail(f"o login do perfil {number} nao foi concluido.")
    return launch(command, profile, rest)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
