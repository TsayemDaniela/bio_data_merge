# define the name of the virtual environment directory
VENV := venv


all: init

init:
	poetry env use ~/.pyenv/shims/python3
	python3 -m pip install setuptools poetry
	# wget https://neo4j.com/artifact.php?name=neo4j-community-5.3.0-unix.tar.gz

install-deps: init
	poetry install

run:
	poetry run python -m bio_data_merge

.PHONY: all run