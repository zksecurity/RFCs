---
title: "Starknet STARK Verifier"
abstract: "In this document we specify the STARK verifier used in Starknet."
sotd: "none"
shortName: "starknet-stark"
editor: "David Wong"
---

## Overview

In this section we give an overview of the STARK protocol.

<aside class="note">Note that the protocol implemented closely resembles the high-level explanations of the <a href="https://eprint.iacr.org/2021/582">ethSTARK paper</a>, as such we refer to it in places.</aside>

<aside class="note">
This protocol is instantiated in several places to our knowledge:
<ul>
    <li><a href="https://github.com/starkware-libs/stone-prover/blob/main/src/starkware/main/cpu/cpu_air_verifier_main.cc">C++ implementation</a></li>
    <li><a href="https://zksecurity.github.io/stark-book/starkex/cairo.html">Solidity implementation</a></li>
    <li><a href="https://github.com/starkware-libs/cairo-lang/tree/9e6e0e96d208608d98635ccfad5b26285c4936e1/src/starkware/cairo/stark_verifier">Cairo0 implementation</a></li>
    <li><a href="https://github.com/HerodotusDev/integrity">Cairo1 implementation</a></li>
</ul>
</aside>

### AIR Arithmetization

TKTK

### Interactive Arithemtization

TKTK

### STARK

TKTK

## Constants

TKTK

## Dependencies

### Hash function

* poseidon with hades permutation (https://docs.orochi.network/poseidon-hash/poseidon-permutation-design/hades-based-design.html ?)

### Channel

See the [Channel specification](channel.html).

### FRI

See the [FRI specification](fri.html).

Specifically, we expose the following functions:

* `fri_commit`
* `fri_verify_initial`
* `fri_verify_step`
* `fri_verify_final`

as well as the two objects `FriVerificationStateConstant, FriVerificationStateVariable` defined in that specification.

## Configuration

```rust
struct StarkConfig {
    traces: TracesConfig,
    composition: TableCommitmentConfig,
    fri: FriConfig,
    proof_of_work: ProofOfWorkConfig,
    // Log2 of the trace domain size.
    log_trace_domain_size: felt252,
    // Number of queries to the last component, FRI.
    n_queries: felt252,
    // Log2 of the number of cosets composing the evaluation domain, where the coset size is the
    // trace length.
    log_n_cosets: felt252,
    // Number of layers that use a verifier friendly hash in each commitment.
    n_verifier_friendly_commitment_layers: felt252,
}
```

To validate:

* proof of work is validated as part of the FRI configuration validation
* compute the log of the evaluation domain size as the log of the trace domain size plus the log of the number of cosets
  * if every coset is of size $2^{n_e}$ with $n_e$ the `log_trace_domain_size`, and there is $2^{n_c}$ cosets, then the evaluation domain size is expected to be $2^{n_e + n_c}$
* traces.validate() (TODO)
* composition.vector.validate()
* the FRI configuration is validated as part of the FRI configuration validation

```rust
        self
            .composition
            .vector
            .validate(log_eval_domain_size, *self.n_verifier_friendly_commitment_layers);

        // Validate Fri config.
        self.fri.validate(*self.log_n_cosets, *self.n_verifier_friendly_commitment_layers);

        // Security bits.
        let n_queries: u32 = (*self.n_queries).try_into().unwrap();
        let log_n_cosets: u32 = (*self.log_n_cosets).try_into().unwrap();
        let proof_of_work_bits: u32 = (*self.proof_of_work.n_bits).try_into().unwrap();

        n_queries * log_n_cosets + proof_of_work_bits
    }
}
```



## Main STARK functions / Buiding blocks

```rust
struct StarkProof {
    config: StarkConfig,
    public_input: PublicInput,
    unsent_commitment: StarkUnsentCommitment,
    witness: StarkWitness,
}

struct StarkUnsentCommitment {
    traces: TracesUnsentCommitment,
    composition: felt252,
    // n_oods_values elements. The i-th value is the evaluation of the i-th mask item polynomial at
    // the OODS point, where the mask item polynomial is the interpolation polynomial of the
    // corresponding column shifted by the corresponding row_offset.
    oods_values: Span<felt252>,
    fri: FriUnsentCommitment,
    proof_of_work: ProofOfWorkUnsentCommitment,
}
```

### Domain

TODO: StarkDomainsImpl::new() 

### STARK commit

1. Absorb the original table with the channel.
2. Sample the interaction challenges (e.g. z and alpha for the memory check argument (different alpha called memory_alpha to distinguish it from the alpha used to aggregate the different constraints into the composition polynomial)).
3. Absorb the interaction table with the channel.
4. Sample the alpha challenge ("composition_alpha") to aggregate all the constraint quotient polynomials (caches the powers of alpha into "traces_coefficients").
5. Absorb the composition columns (the $h_i$ in $h(x) = \sum_i h_i x^i$) with the channel.
6. Sample the oods point (`interaction_after_composition`).
7. Absorb all evaluations with the channel.
8. Verify that the composition polynomial is correct by checking that its evaluation at the oods point is correct using some of the evaluations $\sum_j C_j(\text{oods_point}) = \sum_i h_i(\text{oods_point}) \times \text{oods_point}^i$ (where the left hand side will need evaluations of the trace polynomials (called maks values) and the right hand side will need evaluations of the composition column polynomials, everything is in that oods vector)
9. Sample the oods_alpha challenge with the channel.
10. Call `fri_commit`

### STARK verify (TODO: consolidate with above)

in `src/stark/stark_verify.cairo`:

stark_verify takes these inputs:

* queries (array of FE)
* commitment
* witness
* stark_domains

algorithm:

1. traces_decommit()
2. table_decommit() (different depending on layout)
3. points = queries_to_points(queries, stark_domains)
4. eval_oods_boundary_poly_at_points()
5. fri_verify()

actually, this is wrapped into StarKProofImpl::verify:

1. cfg.validate(security_bits)
2. cfg.public_input.validate(stark_domains)
3. digest = get_public_input_hash(public_input) <-- what is the public input exactly? (should be program + inputs (+outputs?))
4. channel = ChannelImpl::new(digest) <-- statement is a digest of the public_input
5. stark_commitment = stark_commit()
6. queries = generate_queries()
7. stark_verify()

## Full Protocol

The protocol is split into 3 core functions:

* `verify_initial` as defined below.
* `verify_step` is a wrapper around `fri_verify_step` (see the [FRI](#fri) section).
* `verify_final` is a wrapper around `fri_verify_final` (see the [FRI](#fri) section).

One can successively call them in the following order to verify a proof:

1. Call `verify_initial` on the proof and return:
   1. the `FriVerificationStateConstant` object
   2. the `FriVerificationStateVariable` object
   3. the `last_layer_coefficients`
   4. the security bits <-- TODO: remove this?
2. Call verify_step in a loop on each layer of the proof (`n_layers` of them according to the StateConstant returned) and pass the FriVerificationStateVariable in between each calls
3. Call verify_final on the StateConstant and StateVariable objects
4. Enforce that the the StateVariable's iter field is `n_layers + 1`
5. Return the security bits. (TODO: do we need this)

The verify initial function is defined as:

1. Validate the configuration and return the security_bits (TODO: how is security bits calculated).
1. Produce a stark domain object based on the configuration log_trace_domain_size and log_n_coset (TODO:).
1. Validate the public input (TODO: specify an external function for that?).
1. Compute the initial digest as `get_public_input_hash(public_input, cfg.n_verifier_friendly_commitment_layers, settings)` (TODO: define external function for that).
1. Initialize the channel using the digest as defined in the [Channel](#channel) section.
1. Call stark commit as defined in the [STARK commit](#stark-commit) section.
1. Call fri_commit as defined in the [FRI](#fri) section.
1. Call STARK verify as defined in the [STARK verify](#stark-verify) section.
