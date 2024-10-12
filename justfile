
setup:
    pip install -r requirements.txt

build:
    python md2respec.py source/starknet/fri.md > rfcs/starknet/fri.html

watch:
    watchexec -w source/starknet/fri.md -w template.html just build
    