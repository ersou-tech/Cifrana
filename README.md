# Cifrana

Baixa cifras do **CifraClub** e exporta em **ChordPro** — o formato que o
**SongbookPro** importa nativamente.

O CifraClub escreve os acordes numa linha acima da letra; o SongbookPro espera
os acordes embutidos entre colchetes na própria linha. O Cifrana faz essa
conversão de forma **posicional**: cada acorde entra exatamente na coluna em
que estava, então o alinhamento com a sílaba é preservado.

- Sem dependências: só a biblioteca padrão do Python (3.9+).
- Traz título, artista, compositor, tom, capotraste, BPM e afinação.
- Tablaturas viram blocos `{start_of_tab}` / `{end_of_tab}`, sem perder o desenho.
- Uma música, uma lista de músicas ou a página inteira de um artista.
- Transposição opcional, cache em disco e pausa entre requisições.

## Instalação

Basta ter Python 3.9 ou mais novo:

```bash
git clone https://github.com/ersou-tech/cifrana.git
cd cifrana
python -m cifrana --help
```

Se preferir instalar o comando `cifrana` no sistema:

```bash
pip install .
```

## Uso

```bash
# uma música
python -m cifrana https://www.cifraclub.com.br/legiao-urbana/tempo-perdido/

# o atalho artista/musica também funciona
python -m cifrana legiao-urbana/tempo-perdido -o ./cifras

# várias de uma vez, já empacotadas num zip
python -m cifrana legiao-urbana/tempo-perdido skank/vou-deixar --zip cifras.zip

# tudo que aparece na página de um artista
python -m cifrana --artista https://www.cifraclub.com.br/legiao-urbana/ -o ./cifras

# a partir de um arquivo com uma URL por linha
python -m cifrana --lista minhas-musicas.txt -o ./cifras

# transpondo dois semitons acima
python -m cifrana legiao-urbana/tempo-perdido --transpor 2

# só ver o resultado no terminal, sem gravar nada
python -m cifrana legiao-urbana/tempo-perdido --stdout
```

Por padrão os arquivos vão para `./cifras`, com o nome
`Artista - Musica.cho`.

## Como importar no SongbookPro

1. Rode o Cifrana com `--zip cifras.zip` (ou pegue a pasta `cifras/`).
2. Passe os arquivos para o celular/tablet — Google Drive, iCloud, Dropbox,
   e-mail, cabo, o que for mais fácil.
3. No SongbookPro: **Menu → Import**, escolha importar arquivos ou pasta e
   selecione os `.cho` (ou o zip).
4. O SongbookPro lê os `{title}`, `{artist}`, `{key}`, `{capo}` e `{tempo}` e
   já preenche os campos da música — a transposição e o capotraste continuam
   funcionando dentro do app.

Se o seu SongbookPro estiver configurado para outra extensão, use
`--ext .chopro` ou `--ext .pro`.

## Opções

| Opção | O que faz |
| --- | --- |
| `-o, --saida PASTA` | pasta de saída (padrão `./cifras`) |
| `--zip ARQUIVO` | gera também um `.zip` com tudo |
| `--stdout` | imprime no terminal em vez de gravar |
| `--lista ARQUIVO` | lê URLs de um arquivo (`#` vira comentário) |
| `--artista URL` | pega as músicas da página do artista (pode repetir) |
| `--transpor N` | transpõe N semitons (ex.: `2`, `-3`) |
| `--refrao` | usa `{start_of_chorus}`/`{end_of_chorus}` nos refrões |
| `--sem-tabs` | descarta os blocos de tablatura |
| `--sem-fonte` | não inclui o comentário com a URL de origem |
| `--nome MODELO` | modelo do nome do arquivo: `{artist}`, `{title}`, `{key}` |
| `--ext .cho` | extensão dos arquivos gerados |
| `--ascii` | tira acentos dos nomes de arquivo |
| `--sobrescrever` | sobrescreve em vez de criar `(2)` |
| `--intervalo SEG` | pausa entre requisições (padrão `1.0`) |
| `--cache PASTA` / `--sem-cache` / `--recarregar` | controle do cache de HTML |

## Exemplo de saída

```chordpro
{title: Cifra De Teste}
{artist: Banda Ficticia}
{key: G}
{capo: 2}
{tempo: 120}

{comment: Intro}
[G]  [D]  [Em]

{comment: Primeira Parte}
[G]Numero um d[D]ois tres
     [Em]Contando [C]ate seis
```

## Como funciona

1. `urls.py` normaliza qualquer URL do CifraClub para
   `.../artista/musica/imprimir.html` — a versão de impressão entrega a cifra
   em HTML puro, sem depender de JavaScript.
2. `parser.py` lê os blocos `<pre>` (um por página A4) guardando, para cada
   acorde, o nome e a **coluna** em que ele aparece, além dos metadados do
   cabeçalho.
3. `chordpro.py` classifica cada linha (seção, acordes, letra, tablatura,
   vazia), casa cada linha de acordes com a letra logo abaixo e insere os
   `[acordes]` nas colunas certas.
4. `exporter.py` grava os `.cho` com nome seguro (inclusive no Windows) e,
   se você pedir, monta o zip.

## Testes

```bash
python -m unittest discover -s tests -t .
```

Os testes usam um fixture sintético (música inventada), sem conteúdo de
terceiros.

## Aviso

As cifras do CifraClub são de seus autores e editoras. Use esta ferramenta
apenas para uso pessoal, para levar ao seu próprio songbook o que você já tem
direito de acessar, e respeite os termos de uso do site. O `--intervalo`
existe justamente para não sobrecarregar o servidor — não baixe catálogos
inteiros nem redistribua o resultado.
