---
title: "Starknet Channel"
abstract: "TKTK"
sotd: "none"
---

## Overview

A channel is an object that mimics the communication channel between the prover and the verifier, and is used to abstract the [Fiat-Shamir transformation]() used to make the protocol non-interactive (the verifier messages are replaced by sampling a hash function).

A channel is initialized at the beginning of the protocol, and is instantiated with a hash function. It is implemented as a continuous hash that "absorbs" every prover messages and which output can be used to produce the verifier's challenges.

A channel has two fields:

* A **digest**, which represents the current internal state.
* A **counter**, which helps produce different values when the channel is used repeatedly to sample verifier challenges.

The channel has the following interface:

**`init(digest)`**. 

* Initializes the channel with a digest, which is the prologue/context to the protocol. 
* Set the counter to $0$.

**message from prover to verifier**.

* Resets the counter to $0$.
* Set the digest to `POSEIDON_hash(digest + 1 || value)`. (TODO: what if several values)

TODO: explain why the +1

**message from verifier to prover**.

* Produce a random value as `hades_permutation(digest, counter, 2)`.
* Increment the counter.

<aside class="note">With the current design, two different protocols where one produces $n$ challenges and another that produces $m$ challenges will have the same "transcript" and thus will continue to produce the same challenges later on in the protocol. While there are no issues in this design in the context of Starknet, this might not always be secure when used in other protocols.</aside>
