
setup:
    pip install -r requirements.txt
    mkdir -p rfcs/starknet/

build:
    python md2respec.py --output-path rfcs/ --recursive ./source/

debug-build:
    python md2respec.py --pure-html source/starknet/fri.md

serve:
    python -m http.server

watch:
    just serve & watchexec -w md2respec.py -w source/ -w template.html just build
