# define the name of the virtual environment directory
VENV := venv


all: install-deps

init:
	python3 -m pip install setuptools poetry
	poetry env use ~/.pyenv/shims/python3
	# wget https://neo4j.com/artifact.php?name=neo4j-community-5.3.0-unix.tar.gz

install-deps: init
	poetry install

run-processor:
	poetry run python -m bio_data_merge.processor

run-frontend:
	flask --app bio_data_merge.frontend --debug run --port=8000 --host=0.0.0.0

run-utils-overlap:
	poetry run python utils/overlap.py 

.PHONY: all