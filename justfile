
setup:
    pip install -r requirements.txt

build:
    mkdir -p rfcs/starknet/
    python md2respec.py source/starknet/fri.md > rfcs/starknet/fri.html
    python md2respec.py source/starknet/channel.md > rfcs/starknet/channel.html

debug-build:
    python md2respec.py --pure-html source/starknet/fri.md

serve:
    python -m http.server

watch:
    just serve & watchexec -w md2respec.py -w source/starknet/fri.md -w template.html just build
