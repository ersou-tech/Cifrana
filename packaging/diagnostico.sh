#!/usr/bin/env bash
# Mostra todas as instalações do Cifrana que existem nesta máquina e qual
# delas é realmente aberta. Útil quando o programa abre numa versão diferente
# da que o apt diz estar instalada.
#
#   bash packaging/diagnostico.sh
#
# Não altera nada: só lê e relata.

echo "=========== diagnóstico do Cifrana ==========="

echo
echo "-- o que o apt/dpkg acha --"
dpkg-query -W -f='pacote instalado: ${Version}\n' cifrana 2>/dev/null || echo "pacote .deb: não instalado"

echo
echo "-- lançadores encontrados --"
for caminho in /usr/bin/cifrana /usr/bin/cifrana-gui \
               "$HOME/.local/bin/cifrana" "$HOME/.local/bin/cifrana-gui"; do
    [ -e "$caminho" ] && echo "  $caminho"
done

echo
echo "-- atalhos de menu e o que cada um executa --"
for atalho in "$HOME/.local/share/applications/cifrana.desktop" \
              /usr/share/applications/cifrana.desktop; do
    if [ -f "$atalho" ]; then
        echo "  $atalho"
        grep -E "^(Exec|Name)=" "$atalho" | sed 's/^/      /'
    fi
done

echo
echo "-- cópias do código e suas versões --"
achou=0
while IFS= read -r init; do
    [ -f "$init" ] || continue
    achou=1
    versao="$(grep -oP '__version__ = "\K[^"]+' "$init" 2>/dev/null)"
    echo "  ${versao:-?}  ${init%/__init__.py}"
done < <(
    ls -d /usr/lib/python3/dist-packages/cifrana/__init__.py \
          "$HOME"/.local/lib/cifrana/cifrana/__init__.py \
          "$HOME"/.local/lib/python3*/site-packages/cifrana/__init__.py 2>/dev/null
)
[ "$achou" = 1 ] || echo "  (nenhuma encontrada)"

echo
echo "-- qual delas o python carrega de verdade --"
# a partir de /tmp, para o diretório atual não entrar no caminho de busca
(cd /tmp && python3 -c "import cifrana; print('  ' + cifrana.__version__ + '  ' + cifrana.__file__)") 2>/dev/null \
    || echo "  (o python não conseguiu importar o cifrana)"

echo
echo "-- e o que o lançador do sistema abre --"
if [ -x /usr/bin/cifrana ]; then
    echo "  /usr/bin/cifrana --version -> $(cd /tmp && /usr/bin/cifrana --version 2>&1)"
fi

echo
echo "=============================================="
