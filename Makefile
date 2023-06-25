.PHONY: clean distclean run update format

py_files:=update-from-server

default:
	@echo "target required: eg. 'make run' or 'make update'"
	@exit 2

run:
	docker compose up --build

update: venv/.updated
	venv/bin/python3 ./update-from-server

format: venv/.updated
	venv/bin/ruff --config .ruff.toml --cache-dir .git/ruff_cache --fix-only --exit-zero --show-fixes $(py_files)
	venv/bin/black $(py_files)
	venv/bin/isort --multi-line 3 --line-width 88 --trailing-comma --atomic $(py_files)

test: venv/.updated
	venv/bin/ruff --config .ruff.toml --cache-dir .git/ruff_cache $(py_files)
	venv/bin/black --check $(py_files)
	venv/bin/isort --multi-line 3 --line-width 88 --trailing-comma --check-only $(py_files)

venv/.updated: requirements.txt
	[ -e venv/bin/python ] || python3 -m venv venv
	venv/bin/pip install -U pip wheel --disable-pip-version-check
	venv/bin/pip install -U -r requirements.txt
	@touch $@
