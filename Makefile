# Atalhos de desenvolvimento do Cifrana.
PYTHON ?= python3

.PHONY: ajuda test gui deb instalar desinstalar limpar

ajuda:
	@echo "make test         roda os testes"
	@echo "make gui          abre a interface grafica a partir do codigo"
	@echo "make deb          monta o pacote .deb em dist/"
	@echo "make instalar     instala em ~/.local (sem root)"
	@echo "make desinstalar  remove a instalacao de ~/.local"
	@echo "make limpar       apaga dist/, build/ e caches"

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

gui:
	$(PYTHON) -m cifrana.gui

deb:
	./packaging/build-deb.sh

instalar:
	./install.sh

desinstalar:
	./install.sh --remover

limpar:
	rm -rf dist build *.egg-info .cifrana-cache
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
