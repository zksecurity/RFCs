
setup:
    pip install -r requirements.txt

build:
    python md2respec.py source/starknet/fri.md > rfcs/starknet/fri.html

serve:
    python -m http.server

watch:
    just serve & watchexec -w md2respec.py -w source/starknet/fri.md -w template.html just build
