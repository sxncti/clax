#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bin_dir="$HOME/.local/bin"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
lib_dir="$data_dir/clax"
applications_dir="$data_dir/applications"
extensions_dir="$data_dir/gnome-shell/extensions"
extension_uuid="clax-rings@sxncti.github.com"

command -v python3 >/dev/null 2>&1 &&
    python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || {
    printf 'Erro: o CLAX requer Python 3.10 ou mais recente.\n' >&2
    exit 1
}
command -v claude >/dev/null 2>&1 || {
    printf 'Erro: instale o Claude Code antes do CLAX.\n' >&2
    exit 1
}

install -d -m 755 "$bin_dir" "$lib_dir" "$applications_dir" "$extensions_dir/$extension_uuid"
install -m 644 "$project_dir/clax.py" "$project_dir/clax_rings.py" "$lib_dir/"
printf '#!/bin/sh\nexec python3 "%s/clax.py" "$@"\n' "$lib_dir" > "$bin_dir/clax"
chmod 755 "$bin_dir/clax"
sed "s|^Exec=.*|Exec=env CLAX_LAUNCHER=1 $bin_dir/clax|" \
    "$project_dir/clax.desktop" > "$applications_dir/clax.desktop"
chmod 644 "$applications_dir/clax.desktop"
install -m 644 "$project_dir/gnome-extension/extension.js" \
    "$extensions_dir/$extension_uuid/extension.js"
install -m 644 "$project_dir/gnome-extension/metadata.json" \
    "$extensions_dir/$extension_uuid/metadata.json"
install -m 644 "$project_dir/gnome-extension/stylesheet.css" \
    "$extensions_dir/$extension_uuid/stylesheet.css"

"$bin_dir/clax" setup

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$applications_dir"
fi

printf 'CLAX instalado. Rode: clax help\n'
if command -v gnome-extensions >/dev/null 2>&1; then
    printf 'Indicador da topbar instalado. Apos sair e entrar na sessao, ative com:\n'
    printf '  gnome-extensions enable %s\n' "$extension_uuid"
fi
