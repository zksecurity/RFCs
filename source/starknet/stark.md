---
title: "Starknet STARK Verifier"
abstract: "In this document we specify the STARK verifier used in Starknet."
sotd: "draft"
shortName: "starknet-stark"
editor: "David Wong"
tags: ["starknet", "stark", "ethSTARK"]
---

## Overview

<aside class="warning">This specification is work-in-progress.</aside>

<aside class="warning">The protocol specified here is not "zero-knowledge". It is purely aimed at providing succinctness. That is, it is useful to delegate computation.</aside>

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

In this section we give a brief overview of the Starknet STARK protocol.
While the protocol used is designed to verify Cairo programs, we provide an agnostic specification.
The instantiation of this protocol with Cairo should be the object of a different specification.

Before we delve into the details, let's look at the protocol from a high-level protocol diagram point of view. The Starknet STARK protocol is divided in three main phases:

1. Construction of an interactive arithmetization. In this phase the prover commits to different parts of the execution trace it wants to prove, using random challenges in-between.
2. Aggregation of constraints into a composition polynomial. In this phase the prover commits to a composition polynomial that, if checked by FRI, proves that the execution trace satisfies the constraints. It also produces evaluations of commitments at a random point so that the verifier can check that the composition polynomial is well-formed.
3. Aggregation of FRI proofs and FRI protocol. The composition polynomial FRI check as well as evaluation proofs (using FRI-PCS) of all the sent evaluations are aggregtated into a single FRI check. The FRI protocol is then run to verify the aggregated FRI proof. See the [Starknet FRI Verifier specification](fri.html) for more details.

We illustrate the flow in the following diagram:

![STARK overview](/img/starknet/stark_overview.png)

In the next sections we review the different phases.

### Interactive AIR Arithmetization

But first, we quickly remind the reader that the Starknet STARK protocol allows a prover to convince a verifier that an AIR (Algebraic Intermediate Representation) arithmetization is satisfied by their witness. This is generally augmented to also include a public input, usually via a [public memory](https://zksecurity.github.io/stark-book/cairo/memory.html) extension.

AIR is essentially two things:

1. an indexed table representing the execution trace of a run, where columns can be seen as registers and the rows the values they take as one steps through a program. The table takes values when a prover tries to prove an execution. 
2. a list of fixed constraints that are agreed on. 

The indexing of the table is chosen as the elements of the smallest subgroup of power $2$ that can index the table.

Furthermore, the columns of a table can be grouped, which allows the prover to fill the table group by group, using challenges from the verifier in-between. This is useful in order to perform an interactive arithmetization where parts of the encoded circuit needs verifier randomness to be computed.

We give the example of two "original" columns and one "interaction" column, indexed using the multiplicative subgroup of the 16-th roots of unity:

![air](/img/starknet/air.png)

<aside class="example">Here one constraint could be to enforce that `col0[i] + col1[i] - col0[i+1] = 0` on every row `i` except the last one.

As the columns of the table are later interpolated over the index domain, such constraints are usually described and applied as polynomials. So the previous example constraint would look like the following polynomial:

$$\frac{\text{col}_0(x) + \text{col}_1(x) - \text{col}_0(x \cdot w)}{D_0(x)}$$

where the domain polynomial $D_0$ can be efficiently computed as $\frac{x^{16} - 1}{w^{15} - 1}$.</aside>

The first phase of the Starknet STARK protocol is to iteratively construct the trace tables (what we previously called interactive arithmetization). The prover sends commitments to parts of the table, and receives verifier challenges in between.

<aside class="note">In the instantiation of the Starknet STARK protocol, there are only two execution trace tables: the original trace table and the interaction trace table, the verifier challenges received in between is called the interaction challenges. Different Cairo layouts will give place to different trace tables and interaction challenges.</aside>

* TODO: we should make this part agnostic to Cairo though.

### Composition Polynomial

The role of the verifier is now to verify constraints of the form of polynomials on the trace column polynomials, applied on a domain (a list of all the indexes on which the constraint applies).

As with our example above, we can imagine a list of constraints $C_i(x)$ that need to vanish on a list of associated domains described by their domain polynomials $D_i(x)$.

By definition, this can be reduced to checking that you can write each $C_i$ as $C_i(x) = D_i(x) \cdot q(x)$ for some quotient polynomial $q(x)$ of degree $deg(C_i) - deg(D_i)$.

While protocols based on polynomial commitments like KZG would commit to the quotient polynomial and then prove the relation $C_i(x) = D_i(x) \cdot q(x)$ at a random point (using Schwartz-Zippel), the Starknet STARK protocol uses a different approach: it uses a FRI check to prove that the commitment to the evaluations of $q(x) = \frac{C_i(x)}{D_i(x)}$ correctly represents a polynomial of low degree.

As such, the role of the verifier is to verify that all the quotient polynomials associated to all the constraints exist and are of low-degree.

TODO: define low-degree better

As we want to avoid having to go through many FRI checks, the verifier sends a challenge $\alpha$ which the prover can use to aggregate all of the constraint quotient polynomials into a **composition polynomial** $h(x) := \sum_{i=0} \frac{C_i(x)}{D_i(x) \cdot \alpha^i$.

This composition polynomial is quite big, so the prover provides a commitment to chunks or columns of the composition polynomials, interpreting $h$ as $h(x) = \sum_i h_i(x) x^i$.

<aside class="note">In the instantation of this specification with Cairo, there are only two composition column polynomials: $h(x) = h_0(x) + h_1(x) \cdot x$.</aside>

Finally, to allow the verifier to check that $h$ has correctly been committed, Schwartz-Zippel is used with a random verifier challenge called the "oods point". Specifically, the verifier evaluates the following and check that they match:

* the left-hand side $\sum_{i=0} \frac{C_i(\text{oods_point})}{D_i(\text{oods_point})} \cdot \alpha^i$ 
* the right-hand side $h_0(\text{oods_point}) + h_1(\text{oods_point}) \cdot \text{oods_point}$

Of course, the verifier cannot evaluate both sides without the help of the prover! The left-hand side involves evaluations of the trace polynomials at the oods point (and potentially shifted oods points), and the right-hand side involves evaluations of the composition column polynomials at the oods point as well.

As such, the prover sends the needed evaluations to the verifier so that the verifier can perform the check. (These evaluations are often referred to as the "mask" values.)

<aside class="example">
With our previous example constraint, the prover would have to provide the evaluations of $f_0(\text{oods_point}), f_1(\text{oods_point}), f_0(\text{oods_point} \cdot w), h_0(\text{oods_point}), h_1(\text{oods_point})$.
</aside>

Notice that this "oods check" cannot happen in the domain used to index the trace polynomials. This is because the left-hand side involves divisions by domain polynomials $D_i(\text{oods_point})$, which might lead to divisions by zero. 

<aside class="example">If $\text{oods_point} = w^3$ and the second constraint is associated to the whole 16-element domain, then the verifier would have to compute a division with $(w^3)^{16} - 1$ which would be a division by zero.</aside>

This is why the oods point is called "out-of-domain sampling". Although nothing special is done when sampling this point, but the probability that it ends up in the trace domain is very low.

TODO: explain what parts does the term "DEEP" refer to in this protocol.

### Aggregation and FRI Proof

The verifier now has to:

1. Perform a FRI check on $h_0(x) + x h_1(x)$ (which will verify the original prover claim that the trace polynomials satistify the constraints).
2. Verify all the evaluations that were sent, the prover and the verifier can use FRI-PCS for that, as described in [the FRI-PCS section of the Starknet FRI Verifier specification](fri.html#fri-pcs).

TODO: the second point also should have the effect of proving that the commitments to the trace column polynomials are correct (as they will also act as FRI checks)

In order to avoid running multiple instances of the FRI protocol, the FRI Aggregation technique is used as described in [the Aggregating Multiple FRI Proofs section of the Starknet FRI Verifier specification](fri.html#aggregating-multiple-fri-proofs). The verifier sends a challenge called `oods_alpha` which is used to aggregate all of the first layer of the previously discussed FRI proofs.

Finally, the FRI protocol is run as described in [the Starknet FRI Verifier specification](fri.html).

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
  * if every coset is of size $2^{n_t}$ with $n_t$ the `log_trace_domain_size`, and there is $2^{n_c}$ cosets, then the evaluation domain size is expected to be $2^{n_t + n_c}$ (TODO: explain why we talk about cosets here)
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

### Trace and Evaluation Domains

TODO: is this section useful?

There are three types of domains:

1. The trace domain, this is the domain chosen to evaluate the execution trace polynomials. It is typically the smallest subgroup of order $2^{n_t}$ for some $n_t$, such that it can include all the constraints.
2. The evaluation domain, which is chosen as a subgroup of a power of two $2^{n_e}$ that encompasses the trace domain (i.e. $e \geq t$). The "blown up factor" typically dictates how much larger the evaluation domain as a multiple.
(TODO: and then typically moved to a coset). (TODO: why n_cosets then? can this be seen as a union of cosets formed from the trace domain?)

As such, the generator of the trace domain can be found as $\omega_e =3^{(p-1)/n_t}$ (since $\omega_{e}^{n_t} = 1$), and the generator of the evaluation domain can be found as $\omega = 3^{(p-1)/n_e}$.

<aside class="note">The reason for choosing a coset is two-folds. First, in ZK protocols you want to avoid decommitting actual witness values by querying points in the trace domain. Choosing another domain helps but is not sufficient. As this specification does not provide a ZK protocol. The second reason is the one that is interesting to us: it is an optimization reason. As the prover needs to compute the composition polynomial, they can do this in the monomial basis (using vectors of coefficient of the polynomials) but it is expensive. For this reason, they usually operate on polynomials using the lagrange basis (using vectors of evaluations of the polynomials). As such, calculating the composition polynomial leads to divisions by zero if the trace domain is used. The prover could in theory use any other domains, but they decide to use the same domain that they use to commit (the evaluation domain) to avoid having to interpolate and re-evaluate in the domain to commit (which would involve two FFTs).</aside>

### Commitments

Commitments to all the polynomials, before the FRI protocol, are done on evaluations of polynomials in the evaluation domain (as defined in the previous subsection).

Commitments to all the polynomials, before the FRI protocol, are done using table commitments as described in the [Table Commitments section of the Merkle Tree Polynomial Commitments specification](merkle.html#table-commitments).

* For trace polynomials in the interactive arithmetization phase, the tables committed into the leaves represent the evaluations of each of the trace columns at the same point.
* For composition column polynomials in the composition polynomial phase, the tables committed into the leaves represent the evaluations of each of the composition columns at the same point.

### STARK commit

The goal of the STARK commit is to process all of the commitments produced by the prover during the protocol (including the FRI commitments), as well as produce the verifier challenges:

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

### STARK verify

The goal of STARK verify is to verify evaluation queries (by checking that evaluations exist in the committed polynomials) and the FRI queries (by running the FRI verification).

To do this, we simply call the `fri_verify_initial` function contained in the FRI specification, and giving it the following oracle:

The oracle should provide the evaluations, under the same set of FRI queries (and specifically the point they are requesting the evaluations at) of the following polynomials:

* the traces polynomials, which include both the original trace polynomial and the interaction trace polynomial)
* the composition column polynomials

In addition the oracle should verify decommitment proofs (Merkle membership proofs) for each of these evaluations. We refer to the [Merkle Tree Polynomial Commitments specification](merkle.html) on how to verify evaluation proofs.

<aside class="warning">The logic of the oracle must be implemented as part of the verification. The term "oracle" simply refers to an opaque callback function from the FRI protocol's perspective.</aside>

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
1. Call STARK commit as defined in the [STARK commit](#stark-commit) section.
1. Call STARK verify as defined in the [STARK verify](#stark-verify) section.
