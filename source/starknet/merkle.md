---
title: "Starknet Merkle Tree Polynomial Commitments"
abstract: "Merkle tree polynomial commitments provide a standard on how to commit to a polynomial using a Merkle tree."
sotd: "draft"
shortName: "starknet-commit"
editor: "David Wong"
tags: ["starknet", "PCS", "Merkle tree", "hash-based commitments"]
---

## Overview

<aside class="warning">This specification is work-in-progress.</aside>

Commitments of polynomials are done using [Merkle trees](https://en.wikipedia.org/wiki/Merkle_tree). The Merkle trees can be configured to hash some parameterized number of the lower layers using a circuit-friendly hash function (Poseidon).

## Dependencies

* the verifier-friendly hash is `hades_permutation(s1, s2, 2)` always setting the last field element to $2$
* the default hash is either keccak256 or blake2s

## Constants

**`MONTGOMERY_R = 3618502788666127798953978732740734578953660990361066340291730267701097005025`**. The Montgomery form of $2^{256} \mod \text{STARK_PRIME}$.

## Vector Commitments

A vector commitment is simply a Merkle tree. It is configured with two fields:

* `height`: the height of the Merkle tree
* `n_verifier_friendly_commitment_layers`: the depth at which layers will start using the verifier-friendly hash.

<img src="/img/starknet/tree_indexing.png" style="max-width:100%">
<img src="/img/starknet/vector_commit.png" style="max-width:100%">


## Table Commitments

A table commitment in this context is a vector commitment where leaves are hashes of multiple values. Or in other words, a leaf can be seen as a hash of a table of multiple columns and a single row.

It can be configured with two fields:

* `n_columns`: the number of columns in each leaf of the tree
* `vector`: the vector commitment configuration (see previous section).

A few examples:

* the trace polynomials in the [STARK verifier specification](stark.html) are table commitments where each leaf is a hash of the evaluations of all the trace column polynomials at the same point
* the composition polynomial in the [STARK verifier specification](stark.html) is a table commitment where each leaf is a hash of the evaluations of the composition polynomial columns at the same point
* the FRI layer commitments in the [FRI verifier specification](fri.html) are table commitments where each leaf is a hash of the evaluations of the FRI layer columns at associated points (e.g. $v$ and $-v$)

Note that values are multiplied to the `MONTGOMERY_R` constant before being hashed as leaves in the tree. 

TODO: explain why montgomery

## Index to Path Conversion

Random evaluation of the polynomial might produce an index in the range $[0, 2^h)$ with $h$ the height of the tree. Due to the way the tree is indexed, we have to convert that index into a path. To do that, the index is added with the value $2^h$ to set its MSB.

For example, the index `0` becomes the path `10000` which correctly points to the first leaf in our example.

## Vector Membership Proofs

A vector decommitment/membership proof must provide a witness (the neighbor nodes missing to compute the root of the Merkle tree) ordered in a specific way. The following algorithm dictates in which order the nodes hash values provided in the proof are consumed:

<img src="/img/starknet/vector_decommit.png" style="max-width:100%">

## Verifier-Friendly Layers

A `n_verifier_friendly_layers` variable can be passed which dictates at which layer the Merkle tree starts using a verifier-friendly hash.

In the following example, the height of the table commitment is $6$ (and the height of the vector commitment is $5$). As such, a `n_verifier_friendly_layers` of $6$ would mean that only the table would use the verifier-friendly hash. A `n_verifier_friendly_layers` of $5$ would mean that the last / bottom layer of the Merkle tree would also use the verifier-friendly hash. A `n_verifier_friendly_layers` of $1$ would mean that all layers would use the verifier-friendly hash.

<img src="/img/starknet/tree_height.png" style="max-width:100%">

### Note on commitment multiple evaluations under the same leaf

As can be seen in the previous diagram, a leaf can contain (using the technique in [table commitments](#table-commitments)) multiple evaluations of the same polynomial at different points. This is useful for the FRI layer commitments where the same polynomial is evaluated at $v$ and $-v$ (and potentially more values depending on skipped layers).
