# zkSecurity | RFCs

A repository for RFCs related to advanced cryptography.

You can browse the RFCs in the [RFCs](rfcs) directory.

## Build

```
pip install -r requirements.txt
python md2respec.py source/starknet/fri.md  > rfcs/starknet/fri.html
```

TODO: a Makefile that recursively build every RFC in the source/ directory
