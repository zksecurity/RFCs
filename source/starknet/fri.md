---
title: "Starknet FRI Verifier"
abstract: "<p>The <strong>Fast Reed-Solomon Interactive Oracle Proofs of Proximity (FRI)</strong> is a cryptographic protocol that allows a prover to prove to a verifier (in an interactive, or non-interactive fashion) that a hash-based commitment (e.g. a Merkle tree of evaluations) of a vector of values represent the evaluations of a polynomial of some known degree. (That is, the vector committed is not just a bunch of uncorrelated values.) The algorithm is often referred to as a \"low degree\" test, as the degree of the underlying polynomial is expected to be much lower than the degree of the field the polynomial is defined over. Furthermore, the algorithm can also be used to prove the evaluation of a committed polynomial, an application that is often called FRI-PCS. We discuss both algorithms in this document, as well as how to batch multiple instances of the two algorithms.</p>

<p>For more information about the original construction, see <a href=\"https://eccc.weizmann.ac.il/report/2017/134/\">Fast Reed-Solomon Interactive Oracle Proofs of Proximity</a>. This document is about the specific instantiation of FRI and FRI-PCS as used by the StarkNet protocol.</p>

<aside class=\"note\">Specifically, it matches the <a href=\"https://github.com/HerodotusDev/integrity\">integrity verifier</a>, which is a <a href=\"https://book.cairo-lang.org/\">Cairo 1</a> implementation of a Cairo verifier. There might be important differences with the Cairo verifier implemented in C++ or Solidity.</aside>"
sotd: "draft"
shortName: "starknet-fri"
editor: "David Wong"
tags: ["starknet", "fri"]
---

## Overview

<aside class="warning">This specification is work-in-progress.</aside>

We briefly give an overview of the FRI protocol, before specifying how it is used in the StarkNet protocol.

### FRI

<aside class="note">Note that the protocol implemented closely resembles the high-level explanations of the <a href="https://eprint.iacr.org/2021/582">ethSTARK paper</a>, as such we refer to it in places.</aside>

FRI is a protocol that works by successively reducing the degree of a polynomial, and where the last reduction is a constant polynomial of degree $0$. Typically the protocol obtains the best runtime complexity when each reduction can halve the degree of its input polynomial. For this reason, FRI is typically described and instantiated on a polynomial of degree a power of $2$.

If the reductions are "correct", and it takes $n$ reductions to produce a constant polynomial in the "last layer", then it is a proof that the original polynomial at "layer 0" was of degree at most $2^n$.

In order to ensure that the reductions are correct, two mechanisms are used:

1. First, an interactive protocol is performed with a verifier who helps randomize the halving of polynomials. In each round the prover commits to a "layer" polynomial.
2. Second, as commitments are not algebraic objects (as FRI works with hash-based commitments), the verifier query them in multiple points to verify that an output polynomial is consistent with its input polynomial and a random challenge. (Intuitively, the more queries, the more secure the protocol.)

#### Setup

To illustrate how FRI works, one can use [sagemath](https://www.sagemath.org/) with the following setup:

```py
# We use the starknet field (https://docs.starknet.io/architecture-and-concepts/cryptography/p-value/)
starknet_prime = 2^251 + 17*2^192 + 1
starknet_field = GF(starknet_prime)
polynomial_ring.<x> = PolynomialRing(starknet_field)

# find generator of the main group
gen = starknet_field.multiplicative_generator()
assert gen == 3
assert starknet_field(gen)^(starknet_prime-1) == 1 # 3^(order-1) = 1

# lagrange theorem gives us the orders of all the multiplicative subgroups
# which are the divisors of the main multiplicative group order (which, remember, is p - 1 as 0 is not part of it)
# p - 1 = 2^192 * 5 * 7 * 98714381 * 166848103
multiplicative_subgroup_order = starknet_field.order() - 1
assert list(factor(multiplicative_subgroup_order)) == [(2, 192), (5, 1), (7, 1), (98714381, 1), (166848103, 1)]

# find generator of subgroup of order 2^192
# the starknet field has high 2-adicity, which is useful for FRI and FFTs
# (https://www.cryptologie.net/article/559/whats-two-adicity)
gen2 = gen^( (starknet_prime-1) / (2^192) )
assert gen2^(2^192) == 1

# find generator of a subgroup of order 2^i for i <= 192
def find_gen2(i):
    assert i >= 0
    assert i <= 192
    return gen2^( 2^(192-i) )

assert find_gen2(0)^1 == 1
assert find_gen2(1)^2 == 1
assert find_gen2(2)^4 == 1
assert find_gen2(3)^8 == 1
```

#### Reduction

![folding](/img/starknet/folding.png)

A reduction in the FRI protocol is obtained by interpreting an input polynomial $p$ as a polynomial of degree $2n$ and splitting it into two polynomials $g$ and $h$ of degree $n$ such that $p(x) = g(x^2) + x h(x^2)$.

Then, with the help of a verifier's random challenge $\zeta$, we can produce a random linear combination of these polynomials to obtain a new polynomial $g(x) + \zeta h(x)$ of degree $n$:

```py
def split_poly(p, remove_square=True):
    assert (p.degree()+1) % 2 == 0
    g = (p + p(-x))/2 # <---------- nice trick!
    h = (p - p(-x))//(2 * x) # <--- nice trick!
    # at this point g and h are still around the same degree of p
    # we need to replace x^2 by x for FRI to continue (as we want to halve the degrees!)
    if remove_square:
        g = g.parent(g.list()[::2]) # <-- (using python's `[start:stop:step]` syntax)
        h = h.parent(h.list()[::2])
        assert g.degree() == h.degree() == p.degree() // 2
        assert p(7) == g(7^2) + 7 * h(7^2)
    else:
        assert g.degree() == h.degree() == p.degree() - 1
        assert p(7) == g(7) + 7 * h(7)
    return g, h
```

<aside class="note">When instantiating the FRI protocol, like in this specification, the verifier is removed using the <a href="https://en.wikipedia.org/wiki/Fiat%E2%80%93Shamir_heuristic">Fiat-Shamir</a> transformation in order to make the protocol non-interactive.</a></aside>

We can look at the following example to see how a polynomial of degree $7$ is reduced to a polynomial of degree $0$ in 3 rounds:

```py
# p0(x) = 1 + 2x + 3x^2 + 4x^3 + 5x^4 + 6x^5 + 7x^6 + 8x^7
# degree 7 means that we'll get ceil(log2(7)) = 3 rounds (and 4 layers)
p0 = polynomial_ring([1, 2, 3, 4, 5, 6, 7, 8]) 

# round 1: moves from degree 7 to degree 3
h0, g0 = split_poly(p0)
assert h0.degree() == g0.degree() == 3
zeta0 = 3 # <-------------------- the verifier would pick a random zeta
p1 = h0 + zeta0 * g0 # <--------- the prover would send a commitment of p1
assert p0(zeta0) == p1(zeta0^2) # <- sanity check

# round 2: reduces degree 3 to degree 1
h1, g1 = split_poly(p1)
assert g1.degree() == h1.degree() == 1
zeta1 = 12 # <------------ the verifier would pick a random zeta
p2 = h1 + zeta1 * g1 # <-- the prover would send a commitment of p2
assert p1(zeta1) == p2(zeta1^2)
h2, g2 = split_poly(p2)
assert h2.degree() == g2.degree() == 0

# round 3: reduces degree 1 to degree 0
zeta2 = 3920 # <---------- the verifier would pick a random zeta
p3 = h2 + zeta2 * g2 # <-- the prover could send p3 in the clear
assert p2(zeta2) == p3
assert p3.degree() == 0
```

#### Queries

![queries](/img/starknet/queries.png)

In the real FRI protocol, each layer's polynomial would be sent using a hash-based commitment (e.g. a Merkle tree of its evaluations over a large domain). As such, the verifier must ensure that each commitment consistently represents the proper reduction of the previous layer's polynomial. To do that, they "query" commitments of the different polynomials of the different layers at points/evaluations. Let's see how this works.

Given a polynomial $p_0(x) = g_0(x^2) + x h_0(x^2)$ and two of its evaluations at some points $v$ and $-v$, we can see that the verifier can recover the two halves by computing:

* $g_0(v^2) = \frac{p_0(v) + p_0(-v)}{2}$
* $h_0(v^2) = \frac{p_0(v) - p_0(-v)}{2v}$

Then, the verifier can compute the next layer's evaluation at $v^2$ as:

$$
p_{1}(v^2) = g_0(v^2) + \zeta_0 h_0(v^2)
$$

We can see this in our previous example:

```py
# first round/reduction
v = 392 # <-------------------------------------- fake sample a point
p0_v, p0_v_neg = p0(v), p0(-v) # <--------------- the 2 queries we need
g0_square = (p0_v + p0_v_neg)/2
h0_square = (p0_v - p0_v_neg)/(2 * v)
assert p0_v == g0_square + v * h0_square # <------ sanity check
```

In practice, to check that the evaluation on the next layer's polynomial is correct, the verifier would "query" the prover's commitment to the polynomial. These queries are different from the <strong>FRI queries</strong> (which enforce consistency between layers of reductions), they are <strong>evaluation queries or commitment queries</strong> and result in practice in the prover providing a Merkle membership proof (also called decommitment in this specification) to the committed polynomial.

As we already have an evaluation of $v^2$ of the next layer's polynomial $p_1$, we can simply query the evaluation of $p_1(-v^2)$ to continue the **FRI query** process on the next layer, and so on:

```py
p1_v = p1(v^2) # <-------------------------------- query on the next layer
assert g0_square + zeta0 * h0_square == p1_v # <--- the correctness check

# second round/reduction
p1_v_neg = p1(-v^2) # <-- the 1 query we need
g1_square = (p1_v + p1_v_neg)/2 # g1(v^4)
h1_square = (p1_v - p1_v_neg)/(2 * v^2) # h1(v^4)
assert p1_v == g1_square + v^2 * h1_square # p1(v^2) = g1(v^4) + v^2 * h1(v^4)
p2_v = p2(v^4) # <-- query the next layer
assert p2(v^4) == g1_square + zeta1 * h1_square # p2(v^4) = g1(v^4) + zeta1 * h1(v^4)

# third round/reduction
p2_v_neg = p2(-v^4) # <-- the 1 query we need
g2_square = (p2_v + p2_v_neg)/2 # g2(v^8)
h2_square = (p2_v - p2_v_neg)/(2 * v^4) # h2(v^8)
assert p2_v == g2_square + v^4 * h2_square # p2(v^4) = g2(v^8) + v^4 * h2(v^8)
assert p3 == g2_square + zeta2 * h2_square # we already received p3 at the end of the protocol
```

#### Skipping FRI layers

![skipped layers](/img/starknet/skipped_layers.png)

Section 3.11.1 "Skipping FRI Layers" of the ethSTARK paper describes an optimization which skips some of the layers/rounds. The intuition is the following: if we removed the first round commitment (to the polynomial $p_1$), then the verifier would not be able to:

- query $p_1(v^2)$ to verify that layer
- query $p1(-v^2)$ to continue the protocol and get $g_1, h_1$

The first point is fine, as there's nothing to check the correctness of. To address the second point, we can use the same technique we use to compute $p1(v^2)$. Remember, we needed $p_0(v)$ and $p_0(-v)$ to compute $g_0(v^2)$ and $h_0(v^2)$.
But to compute $g_0(-v^2)$ and $h_0(-v^2)$, we need the quadratic residues of $-v^2$, that is $w$, such that $w^2 = -v^2$,
so that we can compute $g_0(-v^2)$ and $h_0(-v^2)$ from $p_0(w)$ and $p_0(-w)$.

We can easily compute them by using $\tau$ (`tau`), the generator of the subgroup of order $4$:

```py
tau = find_gen2(2)
assert tau.multiplicative_order() == 4

# so now we can compute the two roots of -v^2 as
assert (tau * v)^2 == -v^2
assert (tau^3 * v)^2 == -v^2

# and when we query p2(v^4) we can verify that it is correct
# if given the evaluations of p0 at v, -v, tau*v, tau^3*v
p0_tau_v = p0(tau * v)
p0_tau3_v = p0(tau^3 * v)
p1_v_square = (p0_v + p0_v_neg)/2 + zeta0 * (p0_v - p0_v_neg)/(2 * v)
p1_neg_v_square = (p0_tau_v + p0_tau3_v)/2 + zeta0 * (p0_tau_v - p0_tau3_v)/(2 * tau * v)
assert p2(v^4) == (p1_v_square + p1_neg_v_square)/2 + zeta1 * (p1_v_square - p1_neg_v_square)/(2 * v^2)
```

<aside class="note">There is no point producing a new challenge `zeta1` as nothing more was observed from the verifier's point of view during the skipped round. As such, FRI implementations will usually use `zeta0^2` as "folding factor" (and so on if more foldings occur).</aside>

#### Last Layer Optimization

Section 3.11.2 "FRI Last Layer" of the ethSTARK paper describes an optimization which stops at an earlier round. We show this here by removing the last round.

At the end of the second round we imagine that the verifier receives the coefficients of $p_2$ ($h_2$ and $g_2$) directly:

```py
p2_v = h2 + v^4 * g2 # they can then compute p2(v^4) directly
assert g1_square + zeta1 * h1_square == p2_v # and then check correctness
```

### FRI-PCS

Given a polynomial $f$ and an evaluation point $a$, a prover who wants to prove that $f(a) = b$ can prove the related statement for some quotient polynomial $q$ of degree $deg(f) - 1$:

$$
\frac{f(x) - b}{x-a} = q(x)
$$

(This is because if $f(a) = b$ then $a$ should be a root of $f(x) - b$ and thus the polynomial can be factored in this way.)

Specifically, FRI-PCS proves that they can produce such a (commitment to a) polynomial $q$.

### Aggregating Multiple FRI Proofs

To prove that two polynomials $a$ and $b$ exist and are of degree at most $d$, a prover simply shows using FRI that a random linear combination of $a$ and $b$ exists and is of degree at most $d$.

Note that if the FRI check might need to take into account the different degree checks that are being aggregated. For example, if the polynomial $a$ should be of degree at most $d$ but the polynomial should be of degree at most $d+3$ then a degree correction needs to happen. We refer to the [ethSTARK paper](https://eprint.iacr.org/2021/582) for more details as this is out of scope for this specification. (As used in the STARK protocol targeted by this specification, it is enough to show that the polynomials are of low degree.)

## Notable Differences With Vanilla FRI

Besides obvious missing implementation details from the description above, the protocol is pretty much instantiated as is, except for a few changes to the folding and querying process.

As explained above, in the "vanilla FRI" protocol the verifier gets evaluations of $p_0(v)$ and $p_0(-v)$ and computes the next layer's evaluation at $v^2$ as

$$
p_{i+1}(v^2) = \frac{p_{i}(v) + p_{i}(-v)}{2} + \zeta_{i} \frac{p_{i}(v) - p_{i}(-v)}{2v}
$$

which is equivalent to

$$
p_{i+1}(v^2) = g_{i}(v^2) + \zeta_{i} h_{i}(v^2)
$$

where 

$$
p_{i}(x) = g_{i}(x^2) + x h_{i}(x^2)
$$

The first difference in this specification is that, assuming no skipped layers, the folded polynomial is multiplied by 2:

$$
p_{i+1}(x) = 2(g_{i}(x) + \zeta_{i} \cdot h_{i}(x)) 
$$

This means that the verifier has to modify their queries slightly by not dividing by 2:

$$
p_{i+1}(v^2) = p_{i}(v) + p_{i}(-v) + \zeta_{i} \cdot \frac{p_{i}(v) - p_{i}(-v)}{v}
$$

The second difference is that while the evaluations of the first layer $p_0$ happen in a coset called evaluation domain, further evaluations happen in the original (blown up) trace domain (which is avoided for the first polynomial as it might lead to divisions by zero with the polynomials used in the Starknet STARK protocol). To do this, the prover defines the first reduced polynomial as:

$$
p_{1}(x) = 2(g_{0}(9x^2) + \zeta_0 \cdot 3 \cdot h_{0}(9x^2))
$$

Notice that the prover has also multiplied the right term with $3$. This is a minor change that helps with how the verifier code is structured.

This means that the verifier computes the queries on $p_1(x)$ at points on the original subgroup. So the queries of the first layer are produced using $v' = v/3$ (assuming no skipped layers).

$$
p_1((v'^2) = p_0(v) + p_0(-v) + \zeta_0 \cdot \frac{p_0(v) - p_0(-v)}{v'}
$$

<aside class="note">We assume no skipped layers, which is always the case in this specification for the first layer's reduction.</aside>

After that, everything happens as normal (except that now the prover uses the original blown-up trace domain instead of a coset to evaluate and commit to the layer polynomials).

Note that these changes can easily be generalized to work when layers are skipped.

## External Dependencies

In this section we list all the dependencies and interfaces this standard relies on.

### Hash Functions

We rely on two type of hash functions:

* A verifier-friendly hash. Specifically, **Poseidon**. (TODO: explain why, also should we call it circuit-friendly?)
* A standard hash function. Specifically, **Keccak**.

### Channel

See the [Channel](channel.html) specification for details.

### Verifying the first FRI layer

As part of the protocol, the prover must provide a number of evaluations of the first layer polynomial $p_0$ (based on the FRI queries that the verifier generates in the [query phase](#query-phase) of the protocol).

We abstract this here as an oracle that magically provides evaluations. It is the responsibility of the user of this protocol to ensure that the evaluations are correct (which most likely include verifying a number of decommitments). See the [Starknet STARK verifier specification](stark.html) for a concrete usage example.

<aside class="example">For example, the STARK protocol computes evaluations of $p_0(v)$ (but not $p_0(v)$) using decommitments of trace column polynomials and composition column polynomials at the same path corresponding to the evaluation point $v$.</aside>

## Constants

We use the following constants throughout the protocol.

### Protocol constants

**`STARKNET_PRIME = 3618502788666131213697322783095070105623107215331596699973092056135872020481`**. The Starknet prime ($2^{251} + 17 \cdot 2^{192} + 1$).

**`FIELD_GENERATOR = 3`**. The generator for the main multiplicative subgroup of the Starknet field. This is also used as the coset factor to produce the coset used in the first layer's evaluation.

### FRI constants

**`MAX_LAST_LAYER_LOG_DEGREE_BOUND = 15`**. The maximum degree of the last layer polynomial (in log2).

**`MAX_FRI_LAYERS = 15`**. The maximum number of layers in the FRI protocol.

**`MAX_FRI_STEP = 4`**. The maximum number of layers that can be involved in a reduction in FRI (see the overview for more details). This essentially means that each reduction (except for the first as we specify later) can skip 0 to 3 layers.

This means that the standard can be implemented to test that committed polynomials exist and are of degree at most $2^{15 + 15} = 2^{30}$.

### Step Generators And Inverses

As explained in the overview, skipped layers must involve the use of elements of the subgroups of order $2^i$ for $i$ the number of layers included in a step (from 1 to 4 as specified previously).

As different generators can generate the same subgroups, we have to define the generators that are expected. Instead, we define the inverse of the generators of groups of different orders (as it more closely matches the code):

* `const OMEGA_16: felt252 = 0x5c3ed0c6f6ac6dd647c9ba3e4721c1eb14011ea3d174c52d7981c5b8145aa75;`
* `const OMEGA_8: felt252 = 0x446ed3ce295dda2b5ea677394813e6eab8bfbc55397aacac8e6df6f4bc9ca34;`
* `const OMEGA_4: felt252 = 0x1dafdc6d65d66b5accedf99bcd607383ad971a9537cdf25d59e99d90becc81e;`
* `const OMEGA_2: felt252 = -1`

So here, for example, `OMEGA_8` is $1/\omega_8$ where $\omega_8$ is the generator of the subgroup of order $8$ that we later use in the [Verify A Layer's Query](#verify-a-layers-query) section.

## Configuration

### General configuration

The FRI protocol is globally parameterized according to the following variables. For a real-world example, check the [Starknet STARK verifier specification](stark.md).

**`n_verifier_friendly_commitment_layers`**. The number of layers (starting from the bottom) that make use of the circuit-friendly hash.

**`proof_of_work_bits`**. The number of bits required for the proof of work. This value should be between 20 and 50.

### FRI configuration

A FRI configuration contains the following fields:

**`log_input_size`**. The size of the input layer to FRI, specifically the log number of evaluations committed (this should match the log of the evaluation domain size).

**`n_layers`**. The number of layers or folding that will occur as part of the FRI proof. This value must be within the range `[2, MAX_FRI_LAYERS]` (see constants).

**`inner_layers`**. An array of `TableCommitmentConfig` where each configuration represents what is expected of each commitment sent as part of the FRI proof. Refer to the [Table Commitments section of the Starknet Merkle Tree Polynomial Commitments specification](merkle.html#table-commitments).

**`fri_step_sizes`**. The number of layers to skip for each folding/reduction of the protocol. The first step must always be zero, as no layer is skipped during the first reduction. Each step should be within the range `[1, MAX_FRI_STEP]`. For each step, the corresponding layer `inner_layers[i-1]` should have enough columns to support the reduction: `n_columns = 2^fri_step`.

**`log_last_layer_degree_bound`**. The degree of the last layer's polynomial. As it is sent in clear as part of the FRI protocol, this value represents the (log) number of coefficients (minus 1) that the proof will contain. It must be less or equal to `MAX_LAST_LAYER_LOG_DEGREE_BOUND` (see constants).

In addition, the following validations should be performed on passed configurations:

* for every `fri_step_sizes[i]` check:
    * that the previous layer table commitment configuration `inner_Layers[i-1]` has
      * a valid configuration, which can be verified using the expected log input size and the `n_verifier_friendly_commitment_layers`
        * expected log input size should be the input size minus all the step sizes so far
* the `log_expected_input_degree + log_n_cosets == log_input_size`
    * TODO: why is log_n_cosets passed? and what is it? (number of additional cosets with the blowup factor?)
    * where `log_expected_input_degree = sum_of_step_sizes + log_last_layer_degree_bound`

TODO: move these validation steps in the description of the fields above

## Domains and Commitments

There are three types of domains:

The **trace domain**, this is the domain chosen to evaluate the execution trace polynomials. It is typically the smallest subgroup of order $2^{n_t}$ for some $n_t$, such that it can include all the constraints of an AIR constraint system. A generator for the trace domain can be found as $\omega_t =3^{(p-1)/n_t}$ (since $\omega_{t}^{n_t} = 1$)

The **blown-up trace domain**, which is chosen as a subgroup of a power of two $2^{n_e}$ that encompasses the trace domain (i.e. $e \geq t$). The "blown up factor" typically dictates how much larger the evaluation domain is as a multiple. A generator for the blown-up trace domain can be found as $\omega_e = 3^{(p-1)/n_e}$.

The **evaluation domain**, This is a coset of the blown-up domain, computed using the generator of the main group: $\{ 3 \cdot \omega_e^i | i \in [[0, n_e]] \}$.

Commitments are created using table commitments as described in the [Table Commitments section of the Merkle Tree Polynomial Commitments specification](merkle.html#table-commitments).

For the first layer polynomial, the evaluations being committed are in a coset called the evaluation domain.

For all other polynomials, commitments are made up of evaluations in the blown-up trace domain (following the correction outlined in the [Notable Differences With Vanilla FRI](#notable-differences-with-vanilla-fri) section).

<aside class="note">The reason for choosing a coset is two-folds. First, in ZK protocols you want to avoid decommitting actual witness values by querying points in the trace domain. Choosing another domain helps but is not sufficient. As this specification does not provide a ZK protocol. The second reason is the one that is interesting to us: it is an optimization reason. As the prover needs to compute the composition polynomial, they can do this in the monomial basis (using vectors of coefficient of the polynomials) but it is expensive. For this reason, they usually operate on polynomials using the lagrange basis (using vectors of evaluations of the polynomials). As such, calculating the composition polynomial leads to divisions by zero if the trace domain is used. The prover could in theory use any other domains, but they decide to use the same domain that they use to commit (the evaluation domain) to avoid having to interpolate and re-evaluate in the domain to commit (which would involve two FFTs).</aside>

## Protocol

A FRI proof looks like the following:

```rust
struct FriUnsentCommitment {
    // Array of size n_layers - 1 containing unsent table commitments for each inner layer.
    inner_layers: Span<felt252>,
    // Array of size 2**log_last_layer_degree_bound containing coefficients for the last layer
    // polynomial.
    last_layer_coefficients: Span<felt252>,
}
```

The FRI protocol is split into two phases:

1. Commit phase
2. Query phase

We go through each of the phases in the next two subsections.

### Commit Phase

The commit phase processes the `FriUnsentCommitment` object in the following way:

1. Enforce that the first layer has a step size of 0 (`cfg.fri_step_sizes[0] == 0`). (Note that this is mostly to make sure that the prover is following the protocol correctly, as the second layer is never skipped in this standard.)
2. Go through each commitment in order in the `inner_layers` field and perform the following:
   1. Absorb the commitment using the [channel](#channel).
   2. Produce a random challenge.
3. Absorb the `last_layer_coefficients` with the channel.
4. Check that the last layer's degree is correct (according to the configuration `log_last_layer_degree_bound`, see the [Configuration section](#configuration)): `2^cfg.log_last_layer_degree_bound == len(unsent_commitment.last_layer_coefficients)`.
5. return all the random challenges.

### Query Phase

FRI queries are generated once, and then refined through each reduction of the FRI protocol. The number of queries that is pseudo-randomly generated is based on [configuration](#configuration).

Each FRI query is composed of the following fields:

* `index`: the index of the query in the layer's evaluations. Note that this value needs to be shifted before being used as a path in a Merkle tree commitment.
* `y_value`: the evaluation of the layer's polynomial at the queried point.
* `x_inv_value`: the inverse of the point at which the layer's polynomial is evaluated. This value is derived from the `index` as explained in the next subsection.

```rust
struct FriLayerQuery {
    index: felt252,
    y_value: felt252,
    x_inv_value: felt252,
}
```

That is, we should have for each FRI query for the layer $i+1$ the following identity:

$$
p_{i+1}(1/\text{x_inv_value}) = \text{y_value}
$$

Or in terms of commitment, that the decommitment at path `index` is `y_value`.

<aside class="note">This is not exactly correct. The Commitment section explains that `index` points to a point, whereas we need to point to the path in the Merkle tree commitment that gathers its associated points. In addition, `y_value` only gives one evaluation, so the prover will need to witness associated evaluations surrounding the `y_value` as well (see Table Commitment section).</aside>

See the [Converting A Query to a Path section of the Merkle tree specification](merkle.html#converting-a-query-to-a-path) for details.

#### Generating The First Queries

The generation of each FRI query goes through the same process:

* Sample a random challenge from the [channel](#channel).
* Truncate the challenge to obtain the lower 128-bit chunk.
* Reduce it modulo the size of the evaluation domain.

Finally, when all FRI queries have been generated, they are sorted in ascending order.

<aside class="note">This gives you a value that is related to the path to query in a Merkle tree commitment, and can be used to derive the actual evaluation point at which the polynomial is evaluated. Commitments should reveal not just one evaluation, but correlated evaluations in order to help the protocol move forward. For example, if a query is generated for the evaluation point $v$, then the commitment will reveal the evaluation of a polynomial at $v$ but also at $-v$ and potentially more points (depending on the number of layers skipped).</aside>

A query $q$ (a value within $[0, 2^{n_e}]$ for $n_e$ the log-size of the evaluation domain) can be converted to an evaluation point in the following way. First, compute the bit-reversed exponent:

$$
q' = \text{bit_reverse}(q \cdot 2^{64 - n_e})
$$

Then compute the element of the evaluation domain in the coset (with $\omega_e$ the generator of the evaluation domain):

$$
3 \cdot \omega_e^{q'}
$$

TODO: explain why not just do $3 \cdot \omega_e{q}$

Finally, the expected evaluation can be computed using the API defined in the [Verifying the first FRI layer](#verifying-the-first-fri-layer) section.

#### Verify A Layer's Query

Besides the last layer, each layer verification of a query happens by:

1. verifying the query on the current layer. This is done by effectively decommitting a layer's query following the [Merkle Tree Polynomial Commitment](merkle.html) specification.
2. computing the next query as explained below.

We illustrate this in the following diagram, pretending that associated evaluations are not grouped under the same path in the Merkle tree commitment (although in practice they are).

![a FRI query](/img/starknet/query.png)

<aside class="note">This means that when used in the STARK protocol, for example, the first layer represents the same polynomial as the aggregation of a number of FRI checks, and associated evaluations (e.g. $-v$ given $v$) are witnessed. This is akin to a reduction in the FRI protocol (except that the linear combination includes many more terms and scalars).</aside>

To verify the last layer's query, as the last layer polynomial is received in clear, simply evaluate it at the queried point `1/fri_layer_query.x_inv_value` and check that it matches the expected evaluation `fri_layer_query.y_value`.

Each query verification (except on the last layer) will produce queries for the next layer, which will expect specific evaluations.

The next queries are derived as:

* index: `index / coset_size`
* point: `point^coset_size`
* value: see FRI formula below

where coset_size is 2, 4, 8, or 16 depending on the layer (but always 2 for the first layer).

Queries between layers verify that the next layer $p_{i+j}$ is computed correctly based on the current layer $p_{i}$.
The next layer is either the direct next layer $p_{i+1}$ or a layer further away if the configuration allows layers to be skipped.
Specifically, each reduction is allowed to skip 0, 1, 2, or 3 layers (see the `MAX_FRI_STEP` constant).

The FRI formula with no skipping is:

* given a layer evaluations at $\pm v$, a query without skipping layers work this way:
* we can compute the next layer's *expected* evaluation at $v^2$ by computing $p_{i+1}(v^2) = \frac{p_{i}(v)+p_{i}(-v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-v)}{2v}$
* we can then ask the prover to open the next layer's polynomial at that point and verify that it matches

The FRI formula with 1 layer skipped with $\omega_4$ the generator of the 4-th roots of unity (such that $\omega_4^2 = -1$):

* $p_{i+1}(v^2) = \frac{p_{i}(v)+p_{i}(-v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-v)}{2v}$
* $p_{i+1}(-v^2) = \frac{p_{i}(\omega_4 v)+p_{i}(-\omega_4 v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-\omega_4 v)}{2 \cdot \omega_4 \cdot v}$
* $p_{i+2}(v^4) = \frac{p_{i+1}(v^2)+p_{i+1}(-v^2)}{2} + \zeta_i^2 \cdot \frac{p_i(v^2) - p_i(-v^2)}{2 \cdot v^2}$

As you can see, this requires 4 evaluations of p_{i} at $v$, $-v$, $\omega_4 v$, $-\omega_4 v$.

The FRI formula with 2 layers skipped with $\omega_8$ the generator of the 8-th roots of unity (such that $\omega_8^2 = \omega_4$ and $\omega_8^4 = -1$):

* $p_{i+1}(v^2) = \frac{p_{i}(v)+p_{i}(-v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-v)}{2v}$
* $p_{i+1}(-v^2) = \frac{p_{i}(\omega_4 v)+p_{i}(-\omega_4 v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-\omega_4 v)}{2 \cdot \omega_4 \cdot v}$
* $p_{i+1}(\omega_4 v^2) = \frac{p_{i}(\omega_8 v)+p_{i}(- \omega_8 v)}{2} + \zeta_i \cdot \frac{p_i(\omega_8 v) - p_i(- \omega_8 v)}{2 \omega_8 v}$
* $p_{i+1}(-\omega_4 v^2) = \frac{p_{i}(\omega_8^3 v)+p_{i}(- \omega_8^3 v)}{2} + \zeta_i \cdot \frac{p_i(\omega_8^3 v) - p_i(-\omega_8^3 v)}{2 \cdot \omega_8^3 \cdot v}$
* $p_{i+2}(v^4) = \frac{p_{i+1}(v^2)+p_{i+1}(-v^2)}{2} + \zeta_i^2 \cdot \frac{p_{i+1}(v^2) - p_{i+1}(-v^2)}{2 \cdot v^2}$
* $p_{i+2}(-v^4) = \frac{p_{i+1}(\omega_4 v^2)+p_{i+1}(-\omega_4v^2)}{2} + \zeta_i^2 \cdot \frac{p_{i+1}(\omega_4 v^2) - p_{i+1}(-\omega_4 v^2)}{2 \cdot \omega_4 v^2}$
* $p_{i+3}(v^8) = \frac{p_{i+2}(v^4)+p_{i+2}(-v^4)}{2} + \zeta_i^4 \cdot \frac{p_{i+2}(v^4) - p_{i+2}(-v^4)}{2 \cdot v^4}$

As you can see, this requires 8 evaluations of p_{i} at $v$, $-v$, $\omega_4 v$, $-\omega_4 v$, $\omega_8 v$, $- \omega_8 v$, $\omega_8^3 v$, $- \omega_8^3 v$.

The FRI formula with 3 layers skipped with $\omega_{16}$ the generator of the 16-th roots of unity (such that $\omega_{16}^2 = \omega_{8}$, $\omega_{16}^4 = \omega_4$, and $\omega_{16}^8 = -1$):

* $p_{i+1}(v^2) = \frac{p_{i}(v)+p_{i}(-v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-v)}{2v}$
* $p_{i+1}(-v^2) = \frac{p_{i}(\omega_4 v)+p_{i}(-\omega_4 v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-\omega_4 v)}{2 \cdot \omega_4 \cdot v}$
* $p_{i+1}(\omega_4 v^2) = \frac{p_{i}(\omega_8 v)+p_{i}(- \omega_8 v)}{2} + \zeta_i \cdot \frac{p_i(\omega_8 v) - p_i(- \omega_8 v)}{2 \omega_8 v}$
* $p_{i+1}(-\omega_4 v^2) = \frac{p_{i}(\omega_8^3 v)+p_{i}(- \omega_8^3 v)}{2} + \zeta_i \cdot \frac{p_i(\omega_8^3 v) - p_i(-\omega_8^3 v)}{2 \cdot \omega_8^3 \cdot v}$
* $p_{i+1}(\omega_8 v^2) = \frac{p_{i}(\omega_16 v)+p_{i}(- \omega_16 v)}{2} + \zeta_i \cdot \frac{p_i(\omega_16 v) - p_i(- \omega_16 v)}{2 \omega_16 v}$
* $p_{i+1}(-\omega_8 v^2) = \frac{p_{i}(\omega_16^5 v)+p_{i}(- \omega_16^5 v)}{2} + \zeta_i \cdot \frac{p_i(\omega_16^5 v) - p_i(- \omega_16^5 v)}{2 \omega_16^5 v}$
* $p_{i+1}(\omega_8^3 v^2) = \frac{p_{i}(\omega_16^3 v)+p_{i}(- \omega_16^3 v)}{2} + \zeta_i \cdot \frac{p_i(\omega_16^3 v) - p_i(- \omega_16^3 v)}{2 \omega_16^3 v}$
* $p_{i+1}(-\omega_8^3 v^2) = \frac{p_{i}(\omega_16^7 v)+p_{i}(- \omega_16^7 v)}{2} + \zeta_i \cdot \frac{p_i(\omega_16^7 v) - p_i(- \omega_16^7 v)}{2 \omega_16^7 v}$
* $p_{i+2}(v^4) = \frac{p_{i+1}(v^2)+p_{i+1}(-v^2)}{2} + \zeta_i^2 \cdot \frac{p_{i+1}(v^2) - p_{i+1}(-v^2)}{2 \cdot v^2}$
* $p_{i+2}(-v^4) = \frac{p_{i+1}(\omega_4 v^2)+p_{i+1}(-\omega_4v^2)}{2} + \zeta_i^2 \cdot \frac{p_{i+1}(\omega_4 v^2) - p_{i+1}(-\omega_4 v^2)}{2 \cdot \omega_4 v^2}$
* $p_{i+2}(\omega_4 v^4) = \frac{p_{i+1}(\omega_8 v^2)+p_{i+1}(-\omega_8 v^2)}{2} + \zeta_i^2 \cdot \frac{p_{i+1}(\omega_8 v^2) - p_{i+1}(-\omega_8 v^2)}{2 \cdot \omega_8 \cdot v^2}$
* $p_{i+2}(-\omega_4 v^4) = \frac{p_{i+1}(\omega_8^3 v^2)+p_{i+1}(-\omega_8^3 v^2)}{2} + \zeta_i^2 \cdot \frac{p_{i+1}(\omega_8^3 v^2) - p_{i+1}(-\omega_8^3 v^2)}{2 \cdot \omega_8^3 v^2}$
* $p_{i+3}(v^8) = \frac{p_{i+2}(v^4)+p_{i+2}(-v^4)}{2} + \zeta_i^4 \cdot \frac{p_{i+2}(v^4) - p_{i+2}(-v^4)}{2 \cdot v^4}$
* $p_{i+3}(-v^8) = \frac{p_{i+2}(\omega_4 v^4)+p_{i+2}(-\omega_4 v^4)}{2} + \zeta_i^4 \cdot \frac{p_{i+2}(\omega_4 v^4) - p_{i+2}(-\omega_4 v^4)}{2 \cdot \omega_4 v^4}$
* $p_{i+4}(v^16) = \frac{p_{i+3}(v^8)+p_{i+3}(-v^8)}{2} + \zeta_i^8 \cdot \frac{p_{i+3}(v^8) - p_{i+3}(-v^8)}{2 \cdot v^8}$

As you can see, this requires 16 evaluations of p_{i} at $v$, $-v$, $\omega_4 v$, $-\omega_4 v$, $\omega_8 v$, $- \omega_8 v$, $\omega_8^3 v$, $- \omega_8^3 v$, $\omega_16 v$, $-\omega_16 v$, $\omega_16^3 v$, $-\omega_16^3 v$, $\omega_16^5 v$, $-\omega_16^5 v$, $\omega_7 v$, $-\omega_7 v$.

TODO: reconcile with constants used for elements and inverses chosen in subgroups of order $2^i$ (the $\omega$s)

### Proof of work

In order to increase the cost of attacks on the protocol, a proof of work is added at the end of the commitment phase.

Given a 32-bit hash `digest` and a difficulty target of `proof_of_work_bits`, verify the 64-bit proof of work `nonce` by doing the following:

1. Produce a `init_hash = hash_n_bytes(0x0123456789abcded || digest || proof_of_work_bits)` (TODO: endianness)
1. Produce a `hash = hash_n_bytes(init_hash || nonce)` (TODO: endianness)
1. Enforce that the 128-bit high bits of `hash` start with `proof_of_work_bits` zeros (where `proof_of_work_bits` is enforced to be between 20 and 50 as discussed in the [General Configuration section](#general-configuration)).

### Full Protocol

The FRI flow is split into four main functions. The only reason for doing this is that verification of FRI proofs can be computationally intensive, and users of this specification might want to split the verification of a FRI proof in multiple calls.

The four main functions are:

1. `fri_commit`, which returns the commitment to every layers of the FRI proof.
1. `fri_verify_initial`, which returns the initial set of queries to verify the first reduction (Which is special as explained in the [Notable Differences With Vanilla FRI](#notable-differences-with-vanilla-fri) section).
1. `fri_verify_step`, which takes a set of queries and returns another set of queries.
1. `fri_verify_final`, which takes the final set of queries and the last layer coefficients and returns the final result.

To retain context, functions pass around two objects:

```rust
struct FriVerificationStateConstant {
    // the number of layers in the FRI proof (including skipped layers) (TODO: not the first)
    n_layers: u32, 
    // commitments to each layer (excluding the first, last, and any skipped layers)
    commitment: Span<TableCommitment>, 
    // verifier challenges used to produce each (non-skipped) layer polynomial (except the first)
    eval_points: Span<felt252>, 
    // the number of layers to skip for each reduction
    step_sizes: Span<felt252>, 
    // the hash of the polynomial of the last layer
    last_layer_coefficients_hash: felt252, 
}
struct FriVerificationStateVariable {
    // a counter representing the current layer being verified
    iter: u32, 
    // the FRI queries for each (non-skipped) layer
    queries: Span<FriLayerQuery>, 
}
```

<aside note="warning">It is the responsibility of the wrapping protocol to ensure that these three functions are called sequentially, enough times, and with inputs that match the output of previous calls.</aside>

We give more detail to each function below.

**`fri_commit(channel)`**.

1. Take a channel with a prologue (See the [Channel](#channel) section). A prologue contains any context relevant to this proof.
2. Produce the FRI commits according to the [Commit Phase](#commit-phase) section.
3. Produce the proof of work according to the [Proof of Work](#proof-of-work) section.
4. Generate `n_queries` queries in the `eval_domain_size` according to the [Generating Queries](#generating-the-first-queries) section.
5. Convert the queries to evaluation points following the [Converting A Query To An Evaluation Point](#converting-a-query-to-an-evaluation-point) section, producing `points`.
6. Evaluate the first layer at the queried `points` using the external dependency (see [External Dependencies](#external-dependencies) section), producing `values`.
7. Produce the fri_decommitment as `FriDecommitment { values, points }`.

**`fri_verify_initial(queries, fri_commitment, decommitment)`**. Takes the FRI queries, the FRI commitments (each layer's committed polynomial), as well as the evaluation points and their associated evaluations of the first layer (in `decommitment`).

1. Enforce that for each query there is a matching derived evaluation point and evaluation at that point on the first layer contained in the given `decommitment`.
1. Enforce that last layer has the right number of coefficients as expected by the FRI configuration (see the [FRI Configuration](#fri-configuration) section).
1. Compute the first layer of queries as `FriLayerQuery { index, y_value, x_inv_value: 3 / x_value }` for each `x_value` and `y_value` given in the `decommitment`. (This is a correction that will help achieve the differences in subsequent layers outlined in [Notable Differences With Vanilla FRI](#notable-differences-with-vanilla-fri)).
1. Initialize and return the two state objects

```rust
(
    FriVerificationStateConstant {
        n_layers: config.n_layers - 1,
        commitment: fri_commitment.inner_layers, // the commitments
        eval_points: fri_commitment.eval_points, // the challenges
        step_sizes: config.fri_step_sizes[1:], // the number of reduction at each steps
        last_layer_coefficients_hash: hash_array(last_layer_coefficients),
    },
    FriVerificationStateVariable { iter: 0, queries: fri_queries } // the initial queries
)
```

**`fri_verify_step(stateConstant, stateVariable, witness, settings)`**.

1. Enforce that `stateVariable.iter <= stateConstant.n_layers`.
2. Verify the queried layer and compute the next query following the [Verify A Layer's Query](#verify-a-layer-s-query) section.
5. Increment the `iter` counter.
6. Return the next queries and the counter.

**`fri_verify_final(stateConstant, stateVariable, last_layer_coefficients)`**.

1. Enforce that the counter has reached the last layer from the constants (`iter == n_layers`).
1. Enforce that the `last_layer_coefficient` matches the hash contained in the state (TODO: only relevant if we created that hash in the first function).
1. Manually evaluate the last layer's polynomial at every query and check that it matches the expected evaluations.

```rust
fn fri_verify_final(
    stateConstant: FriVerificationStateConstant,
    stateVariable: FriVerificationStateVariable,
    last_layer_coefficients: Span<felt252>,
) -> (FriVerificationStateConstant, FriVerificationStateVariable) {
    assert(stateVariable.iter == stateConstant.n_layers, 'Fri final called at wrong time');
    assert(
        hash_array(last_layer_coefficients) == stateConstant.last_layer_coefficients_hash,
        'Invalid last_layer_coefficients'
    );

    verify_last_layer(stateVariable.queries, last_layer_coefficients);

    (
        stateConstant,
        FriVerificationStateVariable { iter: stateVariable.iter + 1, queries: array![].span(), }
    )
}
```

## Test Vectors

Refer to the reference implementation for test vectors.

## Security Considerations

The current way to compute the bit security is to compute the following formula:

```
n_queries * log_n_cosets + proof_of_work_bits
```

Where:

* `n_queries` is the number of queries generates 
