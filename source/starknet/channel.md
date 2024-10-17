---
title: "Starknet Channels for Fiat-Shamir Instantiation"
abstract: "Channels are an abstraction used to mimic the communication channel between the prover and the verifier in a non-interactive protocol. It is useful to ensure that all prover messages are correctly absorbed before being used by the verifier, and that all verifier challenges are correctly produced."
sotd: "draft"
shortName: "starknet-channel"
editor: "David Wong"
tags: ["starknet", "fiat-shamir"]
---

## Overview

<aside class="warning">This specification is work-in-progress.</aside>

A channel is an object that mimics the communication channel between the prover and the verifier, and is used to abstract the [Fiat-Shamir transformation](https://en.wikipedia.org/wiki/Fiat%E2%80%93Shamir_heuristic) used to make the protocol non-interactive.

The Fiat-Shamir transformation works on public-coin protocols, in which the messages of the verifier are pure random values. To work, the Fiat-Shamir transformation replaces the verifier messages with a hash function applied over the transcript up to that point.

A channel is initialized at the beginning of the protocol, and is instantiated with a hash function. It is implemented as a continuous hash that "absorbs" every prover messages and which output can be used to produce the verifier's challenges.

## Dependencies

A channel is instantiated with the following two dependencies:

* `hades_permutation(s1, s2, s3)`. The hades permutation which permutates a given state of three field elements.
* `poseidon_hash_span(field_elements)`. The poseidon sponge function which hashes a list of field elements.

## Interface

A channel has two fields:

* A **`digest`**, which represents the current internal state.
* A **`counter`**, which helps produce different values when the channel is used repeatedly to sample verifier challenges.

The channel has the following interface:

**Initialize**. This intializes the channel in the following way: 

* Set the `digest` to the given `digest`, which is the prologue/context to the protocol. 
* Set the `counter` to $0$.

**Absorb a message from the prover**.

* Resets the `counter` to $0$.
* Set the `digest` to `POSEIDON_hash(digest + 1 || value)`.

TODO: explain why the +1

**Absorb multiple messages from the prover**.

* Resets the `counter` to $0$.
* Set the `digest` to `POSEIDON_hash(digest + 1 || values)`.

<aside class="warning">This function is not compatible with multiple call to the previous function.</aside>

**Produce a verifier challenge**.

* Produce a random value as `hades_permutation(digest, counter, 2)`.
* Increment the `counter`.

<aside class="warning">With the current design, two different protocols where one produces $n$ challenges and another that produces $m$ challenges will have the same "transcript" and thus will continue to produce the same challenges later on in the protocol. While there are no issues in this design in the context of Starknet, this might not always be secure when used in other protocols.</aside>
