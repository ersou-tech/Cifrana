#!/usr/bin/env bash
# Cria a chave que assina o repositório APT do Cifrana.
#
#   bash packaging/criar-chave-apt.sh
#
# Rode UMA vez, na sua máquina. No fim ele mostra a chave privada para você
# colar em Settings > Secrets and variables > Actions > New repository secret,
# com o nome APT_GPG_KEY. A partir daí o workflow assina o repositório sozinho.
#
# Sem essa chave o repositório funciona igual, mas exige "[trusted=yes]" na
# linha do sources.list — o apt não consegue verificar a autenticidade.
set -euo pipefail

NOME="${NOME:-Cifrana}"
EMAIL="${EMAIL:-cifrana@exemplo.invalid}"
PASTA="$(mktemp -d)"
trap 'rm -rf "$PASTA"' EXIT

export GNUPGHOME="$PASTA"
chmod 700 "$GNUPGHOME"

echo ":: gerando a chave (pode demorar alguns segundos)"
gpg --batch --quiet --gen-key <<EOF
%no-protection
Key-Type: RSA
Key-Length: 4096
Name-Real: $NOME
Name-Email: $EMAIL
Expire-Date: 0
%commit
EOF

IMPRESSAO="$(gpg --list-keys --with-colons "$EMAIL" | awk -F: '/^fpr/{print $10; exit}')"

echo
echo "==================================================================="
echo " 1. Copie TUDO daqui de baixo, inclusive as linhas BEGIN e END:"
echo "==================================================================="
gpg --batch --armor --export-secret-keys "$IMPRESSAO"
echo "==================================================================="
echo
echo " 2. No GitHub, abra:"
echo "      Settings > Secrets and variables > Actions > New repository secret"
echo "    Nome:  APT_GPG_KEY"
echo "    Valor: o bloco acima"
echo
echo " 3. Rode o workflow 'repositorio-apt' (aba Actions > Run workflow)."
echo "    A partir daí o repositório sai assinado e a instrução de instalação"
echo "    publicada na página passa a usar 'signed-by' em vez de 'trusted=yes'."
echo
echo " Impressão digital da chave: $IMPRESSAO"
echo
echo " A chave privada NAO fica guardada nesta máquina: ela existe só no que"
echo " foi mostrado acima e no segredo do GitHub. Guarde uma cópia em lugar"
echo " seguro se quiser poder reusá-la."
