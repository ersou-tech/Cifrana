#!/usr/bin/env bash
# Monta um repositório APT (arquivo "flat") a partir de arquivos .deb.
#
#   packaging/build-apt-repo.sh [PASTA_COM_DEBS] [PASTA_DE_SAIDA]
#
# Padrão: lê de dist/ e escreve em site/.
#
# Se a variável CHAVE_GPG estiver definida, o Release é assinado — é o que
# permite ao apt confiar no repositório sem "[trusted=yes]".
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTRADA="${1:-$RAIZ/dist}"
SAIDA="${2:-$RAIZ/site}"

if ! compgen -G "$ENTRADA/*.deb" > /dev/null; then
    echo "erro: nenhum .deb em $ENTRADA" >&2
    exit 1
fi

for ferramenta in dpkg-scanpackages apt-ftparchive; do
    if ! command -v "$ferramenta" >/dev/null 2>&1; then
        echo "erro: $ferramenta não encontrado (instale dpkg-dev e apt-utils)" >&2
        exit 1
    fi
done

echo ":: montando o repositório em $SAIDA"
rm -rf "$SAIDA"
mkdir -p "$SAIDA"
cp "$ENTRADA"/*.deb "$SAIDA/"

cd "$SAIDA"

# índice dos pacotes (--multiversion mantém as versões antigas disponíveis)
dpkg-scanpackages --multiversion . > Packages
gzip -9nkf Packages

# o Release descreve o repositório e traz os checksums dos índices
apt-ftparchive \
    -o APT::FTPArchive::Release::Origin="Cifrana" \
    -o APT::FTPArchive::Release::Label="Cifrana" \
    -o APT::FTPArchive::Release::Suite="stable" \
    -o APT::FTPArchive::Release::Architectures="all" \
    -o APT::FTPArchive::Release::Components="main" \
    -o APT::FTPArchive::Release::Description="Cifras do CifraClub para o SongbookPro" \
    release . > Release

if [ -n "${CHAVE_GPG:-}" ]; then
    echo ":: assinando com a chave $CHAVE_GPG"
    gpg --batch --yes --local-user "$CHAVE_GPG" --clearsign -o InRelease Release
    gpg --batch --yes --local-user "$CHAVE_GPG" --detach-sign --armor -o Release.gpg Release
    gpg --batch --yes --armor --export "$CHAVE_GPG" > cifrana.asc
    echo ":: chave pública em $SAIDA/cifrana.asc"
else
    echo ":: sem CHAVE_GPG — repositório sem assinatura (exige [trusted=yes])"
fi

# ---- página com as instruções -----------------------------------------
# o texto muda conforme o repositório esteja assinado ou não
BASE="${URL_BASE:-https://ersou-tech.github.io/Cifrana}"
if [ -n "${CHAVE_GPG:-}" ]; then
    LINHA_FONTE="deb [signed-by=/etc/apt/keyrings/cifrana.asc] $BASE ./"
    PASSO_CHAVE="<pre><code>sudo mkdir -p /etc/apt/keyrings
sudo curl -fsSL $BASE/cifrana.asc -o /etc/apt/keyrings/cifrana.asc</code></pre>"
    AVISO=""
else
    LINHA_FONTE="deb [trusted=yes] $BASE ./"
    PASSO_CHAVE=""
    AVISO='<p class="aviso">Este repositório ainda não está assinado, por isso a
      linha usa <code>[trusted=yes]</code>: o apt aceita os pacotes sem verificar
      a assinatura. Para assinar, rode <code>packaging/criar-chave-apt.sh</code>
      e guarde a chave no segredo <code>APT_GPG_KEY</code>.</p>'
fi

VERSOES="$(grep -E "^Version:" Packages | sed 's/Version: //' | sort -Vr | tr '\n' ' ')"

cat > index.html <<HTML
<!doctype html>
<meta charset="utf-8">
<title>Repositório APT do Cifrana</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: system-ui, sans-serif; max-width: 46rem; margin: 3rem auto;
         padding: 0 1.2rem; line-height: 1.6; color: #1c1c1c; }
  h1 { margin-bottom: .2rem; }
  p.sub { color: #5a5a5a; margin-top: 0; }
  pre { background: #f4f4f4; padding: .9rem 1rem; border-radius: 6px;
        overflow-x: auto; border: 1px solid #e0e0e0; }
  code { font-family: ui-monospace, "Roboto Mono", monospace; }
  .aviso { background: #fff8e1; border-left: 4px solid #e0a800;
           padding: .8rem 1rem; border-radius: 0 4px 4px 0; }
  footer { margin-top: 3rem; color: #5a5a5a; font-size: .9rem; }
</style>

<h1>Cifrana</h1>
<p class="sub">Repositório APT — cifras do CifraClub prontas para o SongbookPro</p>

<p>Depois de adicionar este repositório, o Cifrana passa a ser atualizado pelo
<strong>Gerenciador de Atualizações</strong> do Linux Mint, junto com o resto
do sistema.</p>

$AVISO

<h2>Adicionar</h2>
$PASSO_CHAVE
<pre><code>echo "$LINHA_FONTE" | sudo tee /etc/apt/sources.list.d/cifrana.list
sudo apt update
sudo apt install cifrana</code></pre>

<h2>Remover o repositório</h2>
<pre><code>sudo rm /etc/apt/sources.list.d/cifrana.list
sudo apt update</code></pre>

<h2>Versões disponíveis</h2>
<p><code>$VERSOES</code></p>

<footer>
  Código e releases em
  <a href="https://github.com/ersou-tech/Cifrana">github.com/ersou-tech/Cifrana</a>.
</footer>
HTML

echo ":: pacotes publicados:"
grep -E "^(Package|Version):" Packages | paste - - | sed 's/^/   /'
