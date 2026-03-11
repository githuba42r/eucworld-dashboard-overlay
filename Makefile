
BIN=venv/bin

default: test

PYTHONVERSION ?=3.12

PYTHON=python$(PYTHONVERSION)

.PHONY: clean
clean:
	rm -rf build dist *.egg-info

.PHONY: dist
dist:
	$(BIN)/pip install --upgrade twine build
	$(BIN)/python -m build

.PHONY: test
test:
	$(BIN)/pip install -e '.[test]'
	TEST=true $(BIN)/pytest --capture sys --show-capture all tests

.PHONY: ci
ci:
	$(BIN)/pip install -e '.[test]'
	CI=true $(BIN)/pytest --capture sys --show-capture all tests

.PHONY: check
check:
	$(BIN)/pip install -e '.[test]'
	CI=true $(BIN)/pytest --capture sys --show-capture all -m "not gfx"  tests

.PHONY: check-gfx
check-gfx:
	$(BIN)/pip install -e '.[test]'
	$(BIN)/pytest --capture sys --show-capture all -m "gfx"  tests

.PHONY: check-cairo
check-cairo:
	$(BIN)/pip install -e '.[test]'
	$(BIN)/pytest --capture sys --show-capture all -m "cairo"  tests


.PHONY: flake
flake:
	$(BIN)/flake8 gopro_overlay/ --count --select=E9,F63,F7,F82 --show-source --statistics
	$(BIN)/flake8 gopro_overlay/ --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

.PHONY: venv
venv: venv/.installed

venv/.installed:
	@echo python version is $(PYTHONVERSION)
	$(PYTHON) -m venv venv
	touch $@

.PHONY: req
req: venv/.installed
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/pip install -e '.[dev,test]'


.PHONY: test-publish
test-publish: dist
	$(BIN)/pip install twine
	$(BIN)/twine check dist/*
	$(BIN)/twine upload --non-interactive --repository testpypi dist/*


DIST_TEST=tmp/dist-test
CURRENT_VERSION=$(shell PYTHONPATH=. $(PYTHON) -c 'import gopro_overlay.__version__;print(gopro_overlay.__version__.__version__)')

.PHONY: version
version:
	@echo $(CURRENT_VERSION)

.PHONY: test-distribution-install
test-distribution-install: dist
	@echo "Current Version is $(CURRENT_VERSION)"
	rm -rf $(DIST_TEST)
	mkdir -p $(DIST_TEST)
	rm -rf gopro_overlay.egg-info
	$(PYTHON) -m venv $(DIST_TEST)/venv
	$(DIST_TEST)/venv/bin/python -m pip install --upgrade pip
	$(DIST_TEST)/venv/bin/pip install "dist/gopro_overlay-$(CURRENT_VERSION).tar.gz[test]"

.PHONY: test-distribution-test
test-distribution-test:
	PYTHONPATH=. DISTRIBUTION=$(realpath $(DIST_TEST))/venv $(DIST_TEST)/venv/bin/pytest --capture sys --show-capture all tests-dist

.PHONY: test-distribution
test-distribution: test-distribution-install test-distribution-test


.PHONY: ensure-not-released
ensure-not-released:
	$(BIN)/python3 build-scripts/ensure-version-not-released.py $(CURRENT_VERSION)


.PHONY: ensure-pristine
ensure-pristine:
	build-scripts/ensure-working-directory-clean.sh


.PHONY: doc-examples
doc-examples:
	PYTHONPATH=. $(BIN)/python3 build-scripts/generate-examples.py

.PHONY: doc-map-examples
doc-map-examples:
	PYTHONPATH=. $(BIN)/python3 build-scripts/generate-map-examples.py

.PHONY: doc
doc: doc-examples doc-map-examples


.PHONY: publish
publish: ensure-not-released ensure-pristine clean test-distribution
	$(BIN)/pip install --upgrade twine
	$(BIN)/python -m build
	$(BIN)/twine check dist/*
	$(BIN)/twine upload --skip-existing --non-interactive --repository pypi dist/*
	git tag v$(CURRENT_VERSION)


.PHONY: bump
bump:
	$(BIN)/pip install bump-my-version
	$(BIN)/bump-my-version bump minor

.PHONY: bump-major
bump-major:
	$(BIN)/pip install bump-my-version
	$(BIN)/bump-my-version bump major


.PHONY: help
help:
	PYTHONPATH=. $(BIN)/python bin/gopro-contrib-data-extract.py --help
	PYTHONPATH=. $(BIN)/python bin/gopro-cut.py --help
	PYTHONPATH=. $(BIN)/python bin/gopro-dashboard.py --help
	PYTHONPATH=. $(BIN)/python bin/gopro-extract.py --help
	PYTHONPATH=. $(BIN)/python bin/gopro-join.py --help
	PYTHONPATH=. $(BIN)/python bin/gopro-rename.py --help
	PYTHONPATH=. $(BIN)/python bin/gopro-to-csv.py --help
	PYTHONPATH=. $(BIN)/python bin/gopro-to-gpx.py --help
