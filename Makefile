pyupgrade = pyupgrade --py311-plus $$(find inmanta_plugins tests -type f -name '*.py')
flake8 = flake8 inmanta_plugins tests 
black = black inmanta_plugins tests
black_preview = black --preview inmanta_plugins tests
isort = isort inmanta_plugins tests


.PHONY: install
install:
	pip install -U --upgrade-strategy=eager pip setuptools wheel
	pip install -U --upgrade-strategy=eager -e . -c requirements.txt -r requirements.dev.txt


.PHONY: format
format:
	$(isort)
	$(black_preview)
	$(black)
	$(flake8)
	$(pyupgrade)


.PHONY: pep8
pep8:
	$(flake8)
	$(pyupgrade)

SET_UP_MYPY_PLUGINS=mkdir -p mypy/out
RUN_MYPY_PLUGINS=python -m mypy --namespace-packages -p inmanta_plugins.sops
RUN_MYPY_TESTS=MYPYPATH=tests python -m mypy --html-report mypy/out/tests tests

mypy-plugins:
	@ echo -e "Running mypy on the module plugins\n..."
	@ $(SET_UP_MYPY_PLUGINS)
	@ $(RUN_MYPY_PLUGINS) --html-report mypy/out/inmanta_plugins

mypy-tests:
	@ echo -e "Running mypy on the module tests\n..."
	@ $(SET_UP_MYPY_PLUGINS)
	@ $(RUN_MYPY_TESTS)

.PHONY: mypy
mypy: mypy-plugins mypy-tests

mypy-baseline:
	$(RUN_MYPY_PLUGINS) | mypy-baseline filter

mypy-baseline-sync:
	$(RUN_MYPY_PLUGINS) | mypy-baseline sync

ci-mypy: mypy-baseline