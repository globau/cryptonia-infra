.PHONY: clean distclean run update

default:
	@echo "target required: eg. 'make run' or 'make update'"
	@exit 2

run:
	docker compose up --build

update: venv/.updated
	venv/bin/python3 ./update-from-server

venv/.updated: requirements.txt
	[ -e venv/bin/python ] || python3 -m venv venv
	venv/bin/pip install -U pip wheel --disable-pip-version-check
	venv/bin/pip install -U -r requirements.txt
	@touch $@
