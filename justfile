default:
    @just --list

install:
    mise install
    mise exec -- python -m venv .venv
    .venv/bin/pip install -r requirements.txt

run:
    .venv/bin/python -m src.main
