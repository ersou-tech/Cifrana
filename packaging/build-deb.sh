#!/usr/bin/env bash
# Monta o pacote .deb do Cifrana em dist/.
# Uso: ./packaging/build-deb.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

VERSAO="$(python3 -c "import re,pathlib; print(re.search(r'__version__ = \"([^\"]+)\"', pathlib.Path('cifrana/__init__.py').read_text()).group(1))")"
PACOTE="cifrana_${VERSAO}_all"
BUILD="dist/${PACOTE}"

echo ":: montando cifrana ${VERSAO}"
rm -rf "$BUILD"
mkdir -p \
  "$BUILD/DEBIAN" \
  "$BUILD/usr/bin" \
  "$BUILD/usr/lib/python3/dist-packages/cifrana" \
  "$BUILD/usr/share/applications" \
  "$BUILD/usr/share/icons/hicolor/scalable/apps" \
  "$BUILD/usr/share/doc/cifrana" \
  "$BUILD/usr/share/man/man1"

# ---- código -----------------------------------------------------------
install -m 644 cifrana/*.py "$BUILD/usr/lib/python3/dist-packages/cifrana/"

# ---- executáveis ------------------------------------------------------
cat > "$BUILD/usr/bin/cifrana" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 -m cifrana "$@"
EOF

cat > "$BUILD/usr/bin/cifrana-gui" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 -m cifrana.gui "$@"
EOF

chmod 755 "$BUILD/usr/bin/cifrana" "$BUILD/usr/bin/cifrana-gui"

# ---- integração com o desktop ----------------------------------------
install -m 644 packaging/cifrana.desktop "$BUILD/usr/share/applications/cifrana.desktop"
install -m 644 packaging/cifrana.svg "$BUILD/usr/share/icons/hicolor/scalable/apps/cifrana.svg"

# ---- documentação -----------------------------------------------------
install -m 644 packaging/copyright "$BUILD/usr/share/doc/cifrana/copyright"
install -m 644 README.md "$BUILD/usr/share/doc/cifrana/README.md"
gzip -9nc packaging/changelog.Debian > "$BUILD/usr/share/doc/cifrana/changelog.Debian.gz"
chmod 644 "$BUILD/usr/share/doc/cifrana/changelog.Debian.gz"
gzip -9nc packaging/cifrana.1 > "$BUILD/usr/share/man/man1/cifrana.1.gz"
chmod 644 "$BUILD/usr/share/man/man1/cifrana.1.gz"

# ---- metadados --------------------------------------------------------
TAMANHO="$(du -ks "$BUILD" | cut -f1)"
sed -e "s/@VERSAO@/${VERSAO}/" -e "s/@TAMANHO@/${TAMANHO}/" \
  packaging/control.in > "$BUILD/DEBIAN/control"
install -m 755 packaging/postinst "$BUILD/DEBIAN/postinst"
install -m 755 packaging/postrm "$BUILD/DEBIAN/postrm"

# ---- empacota ---------------------------------------------------------
dpkg-deb --build --root-owner-group "$BUILD" > /dev/null
rm -rf "$BUILD"

echo ":: pronto -> dist/${PACOTE}.deb"
dpkg-deb --info "dist/${PACOTE}.deb" | sed -n '2,12p'
