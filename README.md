# zkSecurity | RFCs

A repository for RFCs related to advanced cryptography.

You can browse the RFCs in the [RFCs](rfcs) directory.

## Setup & Build

setup and build with [just](https://github.com/casey/just):

```shell
just setup
just build
just serve # this will serve on localhost:8000/rfcs/starknet/fri.html
```

> [!NOTE]  
> TODO: a Makefile that recursively build every RFC in the source/ directory

watch for any changes with [watchexec](https://github.com/watchexec/watchexec):

```shell
just watch # this will also serve on localhost:8000/rfcs/starknet/fri.html
```
