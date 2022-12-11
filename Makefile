# define the name of the virtual environment directory
VENV := venv


all: init

init:
	poetry env use ~/.pyenv/shims/python3
	python3 -m pip install setuptools poetry

install-deps: init
	poetry install

run:
	poetry run python -m bio_data_merge

.PHONY: all run