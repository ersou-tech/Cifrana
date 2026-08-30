#!/usr/bin/env bash
# Instala o Cifrana para o usuario atual, sem precisar de root.
#
#   ./install.sh              instala em ~/.local
#   ./install.sh --remover    desinstala
#
# Se voce prefere um pacote do sistema, use o .deb:
#   ./packaging/build-deb.sh && sudo apt install ./dist/cifrana_*.deb
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIXO="${PREFIXO:-$HOME/.local}"
LIB="$PREFIXO/lib/cifrana"
BIN="$PREFIXO/bin"
APPS="$PREFIXO/share/applications"
ICONES="$PREFIXO/share/icons/hicolor/scalable/apps"

remover() {
    rm -rf "$LIB"
    rm -f "$BIN/cifrana" "$BIN/cifrana-gui"
    rm -f "$APPS/cifrana.desktop" "$ICONES/cifrana.svg"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$APPS" || true
    echo ":: Cifrana removido de $PREFIXO"
}

if [ "${1:-}" = "--remover" ] || [ "${1:-}" = "--uninstall" ]; then
    remover
    exit 0
fi

# ---- checagens --------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "erro: python3 nao encontrado. Instale com: sudo apt install python3" >&2
    exit 1
fi

VERSAO_OK="$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 9) else 0)')"
if [ "$VERSAO_OK" != "1" ]; then
    echo "erro: e necessario Python 3.9 ou mais novo (achei $(python3 -V))" >&2
    exit 1
fi

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    echo "O Tkinter nao esta instalado — sem ele a interface grafica nao abre."
    if [ -t 0 ] && command -v apt >/dev/null 2>&1; then
        printf "Instalar agora com 'sudo apt install python3-tk'? [S/n] "
        read -r resposta
        case "$resposta" in
            [Nn]*)
                echo ":: seguindo sem a interface grafica (o comando de terminal funciona)"
                ;;
            *)
                sudo apt install -y python3-tk \
                    || echo ":: nao consegui instalar; rode depois: sudo apt install python3-tk"
                ;;
        esac
    else
        echo "   instale com:  sudo apt install python3-tk"
    fi
    echo
fi

# ---- conflito com o pacote do sistema ---------------------------------
# Os dois atalhos se chamam cifrana.desktop e, pelo padrão XDG, o do usuário
# substitui o do sistema por inteiro. Instalar aqui por cima de um pacote .deb
# faz o menu abrir esta cópia e ignorar a do sistema — inclusive quando o apt
# atualizar o pacote, o que deixa o programa "preso" numa versão antiga.
# "-W" sozinho não serve: um pacote removido sem purge continua no banco do
# dpkg (estado config-files) e faria o aviso disparar à toa.
if [ "$(dpkg-query -W -f='${db:Status-Status}' cifrana 2>/dev/null)" = "installed" ]; then
    VERSAO_DEB="$(dpkg-query -W -f='${Version}' cifrana 2>/dev/null)"
    echo "Atenção: o pacote cifrana $VERSAO_DEB já está instalado no sistema."
    echo
    echo "  Instalar aqui em $PREFIXO faz o menu abrir ESTA cópia e ignorar a"
    echo "  do sistema — inclusive depois que o apt atualizar o pacote."
    echo
    echo "  Se você quer o que o apt instalou, não precisa deste script:"
    echo "  o programa já está no menu."
    echo
    if [ -t 0 ]; then
        printf "Instalar assim mesmo? [s/N] "
        read -r resposta
        case "$resposta" in
            [Ss]*) echo ;;
            *) echo ":: cancelado"; exit 0 ;;
        esac
    else
        echo ":: cancelado (rode com um terminal interativo para confirmar)"
        exit 0
    fi
fi

# ---- instala ----------------------------------------------------------
echo ":: instalando em $PREFIXO"
rm -rf "$LIB"
mkdir -p "$LIB/cifrana" "$BIN" "$APPS" "$ICONES"
install -m 644 "$RAIZ"/cifrana/*.py "$LIB/cifrana/"

cat > "$BIN/cifrana" <<EOF
#!/bin/sh
PYTHONPATH="$LIB\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m cifrana "\$@"
EOF

cat > "$BIN/cifrana-gui" <<EOF
#!/bin/sh
PYTHONPATH="$LIB\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m cifrana.gui "\$@"
EOF

chmod 755 "$BIN/cifrana" "$BIN/cifrana-gui"

install -m 644 "$RAIZ/packaging/cifrana.svg" "$ICONES/cifrana.svg"
sed "s|^Exec=cifrana-gui$|Exec=$BIN/cifrana-gui|" \
    "$RAIZ/packaging/cifrana.desktop" > "$APPS/cifrana.desktop"
chmod 644 "$APPS/cifrana.desktop"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$APPS" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -q -f -t "$PREFIXO/share/icons/hicolor" || true

echo ":: pronto"
echo
echo "   Menu:     procure por 'Cifrana'"
echo "   Terminal: cifrana --help   |   cifrana-gui"

case ":$PATH:" in
    *":$BIN:"*) ;;
    *)
        echo
        echo "   Atencao: $BIN nao esta no seu PATH."
        echo "   Acrescente ao ~/.bashrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac
