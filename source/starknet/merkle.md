---
title: "Starknet Merkle Tree Polynomial Commitments"
abstract: "TKTK"
sotd: "draft"
shortName: "starknet-commit"
editor: "David Wong"
tags: ["starknet", "PCS", "Merkle tree", "hash-based commitments"]
---

## Overview

Commitments of polynomials are done using [Merkle trees](). The Merkle trees can be configured to hash some parameterized number of the lower layers using a circuit-friendly hash function (Poseidon).

* TODO: why montgomery form?

## Dependencies

TODO: hash

## Table commitments

A table commitment in this context is a vector commitment where leaves are potentially hashes of several values (tables of multiple columns and a single row).

## Vector commitments

A vector commitment is simply a Merkle tree. 

![tree indexing](/img/starknet/fri/tree_indexing.png)

![vector commit](/img/starknet/fri/vector_commit.png)

## Index to Path conversion

Random evaluation of the polynomial might produce an index in the range $[0, 2^h)$ with $h$ the height of the tree. Due to the way the tree is indexed, we have to convert that index into a path. To do that, the index is added with the value $2^h$ to set its MSB.

For example, the index `0` becomes the path `10000` which correctly points to the first leaf in our example.

## Vector membership proofs

A vector decommitment/membership proof must provide a witness (the neighbor nodes missing to compute the root of the Merkle tree) ordered in a specific way. The following algorithm dictates in which order the nodes hash values provided in the proof are consumed:

![vector decommit](/img/starknet/fri/vector_decommit.png)

## Verifier-Friendly Layers

A `n_verifier_friendly_layers` variable can be passed which dictates at which layer the Merkle tree starts using a verifier-friendly hash.

In the following example, the height of the table commitment is $6$ (and the height of the vector commitment is $5$). As such, a `n_verifier_friendly_layers` of $6$ would mean that only the table would use the verifier-friendly hash. A `n_verifier_friendly_layers` of $5$ would mean that the last / bottom layer of the Merkle tree would also use the verifier-friendly hash. A `n_verifier_friendly_layers` of $1$ would mean that all layers would use the verifier-friendly hash.

![vector decommit](/img/starknet/fri/tree_height.png)

### Note on commitment multiple evaluations under the same leaf

* the following array contains all the 16-th roots of unity, handily ordered
* that is, the first represents the subgroup of order 1, the two first values represent the subgroup of order 2, the four first values represent the subgroup of order 4, and so on
* furthermore, these values are chosen in relation to how evaluations are ordered in a leaf of a commitment
* each value tells you exactly what to multiply to 1/(something*x) to obtain 1/(x)
* TODO: but wait, how is inv_x obtained... that doesn't make sense no?
* it seems like the following values are used to "correct" the x value depending on where x pointed at

```
array![
    0x1,
    0x800000000000011000000000000000000000000000000000000000000000000,
    0x625023929a2995b533120664329f8c7c5268e56ac8320da2a616626f41337e3,
    0x1dafdc6d65d66b5accedf99bcd607383ad971a9537cdf25d59e99d90becc81e,
    0x63365fe0de874d9c90adb1e2f9c676e98c62155e4412e873ada5e1dee6feebb,
    0x1cc9a01f2178b3736f524e1d06398916739deaa1bbed178c525a1e211901146,
    0x3b912c31d6a226e4a15988c6b7ec1915474043aac68553537192090b43635cd,
    0x446ed3ce295dda2b5ea677394813e6eab8bfbc55397aacac8e6df6f4bc9ca34,
    0x5ec467b88826aba4537602d514425f3b0bdf467bbf302458337c45f6021e539,
    0x213b984777d9556bac89fd2aebbda0c4f420b98440cfdba7cc83ba09fde1ac8,
    0x5ce3fa16c35cb4da537753675ca3276ead24059dddea2ca47c36587e5a538d1,
    0x231c05e93ca34c35ac88ac98a35cd89152dbfa622215d35b83c9a781a5ac730,
    0x00b54759e8c46e1258dc80f091e6f3be387888015452ce5f0ca09ce9e571f52,
    0x7f4ab8a6173b92fda7237f0f6e190c41c78777feabad31a0f35f63161a8e0af,
    0x23c12f3909539339b83645c1b8de3e14ebfee15c2e8b3ad2867e3a47eba558c,
    0x5c3ed0c6f6ac6dd647c9ba3e4721c1eb14011ea3d174c52d7981c5b8145aa75,
]
```

* that is, if x pointed at the beginning of a coset, then we don't need to correct it (the first evaluation committed to contains x)
* but if x pointed at the first value, it actually points to an evaluation of -x, so we need to correct the -x we have by multiplying with -1 again so that we get x (or -1/x becomes 1/x, same thing)
* if x points to the 2 value, then 