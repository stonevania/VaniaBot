.PHONY: venv build run

venv:
	python3 -m venv venv

build: venv
	./venv/bin/python -m pip install -r requirements.txt

run: build
	./venv/bin/python main.py