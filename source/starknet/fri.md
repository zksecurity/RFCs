---
title: "Starknet FRI Verifier"
abstract: "<p>The <strong>Fast Reed-Solomon Interactive Oracle Proofs of Proximity (FRI)</strong> is a cryptographic protocol that allows a prover to prove to a verifier (in an interactive, or non-interactive fashion) that a hash-based commitment (e.g. a Merkle tree of evaluations) of a vector of values represent the evaluations of a polynomial of some known degree. (That is, the vector committed is not just a bunch of uncorrelated values.) The algorithm is often referred to as a \"low degree\" test, as the degree of the underlying polynomial is expected to be much lower than the degree of the field the polynomial is defined over. Furthermore, the algorithm can also be used to prove the evaluation of a committed polynomial, an application that is often called FRI-PCS. We discuss both algorithms in this document, as well as how to batch multiple instances of the two algorithms.</p>

<p>For more information about the original construction, see <a href=\"https://eccc.weizmann.ac.il/report/2017/134/\">Fast Reed-Solomon Interactive Oracle Proofs of Proximity</a>. This document is about the specific instantiation of FRI and FRI-PCS as used by the StarkNet protocol.</p>

<aside class=\"note\">Specifically, it matches the [integrity verifier](https://github.com/HerodotusDev/integrity/tree/main/src) which is a Cairo implementation of a Cairo verifier. There might be important differences with the Cairo verifier implemented in C++ or Solidity.</aside>"
sotd: "none"
---

## Overview

We briefly give an overview of the FRI protocol, before specifying how it is used in the StarkNet protocol.

### FRI

<aside class="note">Note that the protocol implemented closely resembles the high-level explanations of the <a href="https://eprint.iacr.org/2021/582">ethSTARK paper</a>, as such we refer to it in places.</aside>

FRI is a protocol that works by successively reducing the degree of a polynomial, and where the last reduction is a constant polynomial of degree $0$. Typically the protocol obtains the best runtime complexity when each reduction can halve the degree of its input polynomial. For this reason, FRI is typically described and instantiated on a polynomial of degree a power of $2$.

If the reductions are "correct", and it takes $n$ reductions to produce a constant polynomial in the "last layer", then it is a proof that the original polynomial at "layer 0" was of degree at most $2^n$.

In order to ensure that the reductions are correct, two mechanisms are used:

1. First, an interactive protocol is performed with a verifier who helps randomizing the halving of polynomials. In each round the prover commits to a "layer" polynomial.
2. Second, as commitments are not algebraic objects (as FRI works with hash-based commitments), the verifier query them in multiple points to verify that an output polynomial is consistant with its input polynomial and a random challenge. (Intuitively, the more queries, the more secure the protocol.)

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

# lagrange theorem's gives us the orders of all the multiplicative subgroups
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

![folding](/img/starknet/fri/folding.png)

A reduction in the FRI protocol is obtained by interpreting an input polynomial $p$ as a polynomial of degree $2n$ and splitting it into two polynomials $g$ and $h$ of degree $n$ such that $p(x) = g(x^2) + x h(x^2)$.

Then, with the help of a verifier's random challenge $\zeta$, we can produce a random linear combination of these polynomials to obtain a new polynomial $g(x) + \zeta h(x)$ of degree $n$:

```py
def split_poly(p, remove_square=True):
    assert (p.degree()+1) % 2 == 0
    g = (p + p(-x))/2 # <---------- nice trick!
    h = (p - p(-x))//(2 * x) # <--- nice trick!
    # at this point g and h are still around the same degree of p
    # we need to replace x^2 by x for FRI to (as we want to halve the degrees!)
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

![queries](/img/starknet/fri/queries.png)

In the real FRI protocol, each layer's polynomial would be sent using a hash-based commitment (e.g. a Merkle tree of its evaluations over a large domain). As such, the verifier must ensure that each commitment consistently represent the proper reduction of the previous layer's polynomial. To do that, they "query" commitments of the different polynomials of the different layers at points/evaluations. Let's see how this works.

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

![skipped layers](/img/starknet/fri/skipped_layers.png)

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

#### Commitments

Commitments used in this specification are Merkle tree commitments of evaluations of a polynomial. In other words, the leaves of the Merkle tree are evaluations of a polynomial at distinct points.

We use a coset to evaluate the polynomial at the different points. This is for two reasons:

1. In FRI we can increase the size of the evaluated domain in the commitments, in order to decrease the number of queries needed to ensure high bit-security. (TODO: how do cosets help us here?)
2. As used in Starknet STARK (TODO: link to the STARK verifier specification), the layer 0 polynomial has to be computed as a rational polynomial that would lead to division by zero issues if evaluated in the original evaluation domain. As such we take a coset to avoid this issue.

As with what we specify in the rest of this document, we produce a coset of the same size as the evaluation domain (the domain which is used to produce the layer 0 polynomial in the Starknet STARK protocol).

```py
# if we evaluate the polynomial on a set of size 8 (so the blowup factor is 1)
g = find_gen2(log(8,2))

coset = [3 * g^i for i in range(8)] 
poly8_evals = [p0(x) for x in coset] # <-- we would merklelify this as statement
```

### FRI-PCS

Given a polynomial $f$ and an evaluation point $a$, a prover who wants to prove that $f(a) = b$ can prove the related statement for some quotient polynomial $q$ of degree $deg(f) - 1$:

$$
\frac{f(x) - b}{x-a} = q(x)
$$

(This is because if $f(a) = b$ then $a$ should be a root of $f(x) - b$ and thus the polynomial can be factored in this way.)

Specifically, FRI-PCS proves that they can produce such a (commitment to a) polynomial $q$.

### Aggregating multiple FRI proofs

To prove that two polynomials $a$ and $b$ exist and are of degree at most $d$, a prove simply prove that a random linear combination of $a$ and $b$ exists and is of degree at most $d$.

TODO: what if the different polynomials are of different degrees?

TODO: we do not make use of aggregation here, the way the first layer polynomial is created is sort of transparent here, is it still worth having this section?

## Notable differences with vanilla FRI

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
p_{i+1}(x) = 2(g_{i}(x) + \zeta_{i} \cdot 3^{-1} \cdot h_{i}(x)) 
$$

This means that the verifier has to modify their queries slightly by not dividing by 2:

$$
p_{i+1}(v^2) = p_{i}(v) + p_{i}(-v) + \zeta_{i} g \cdot \frac{p_{i}(v) - p_{i}(-v)}{v}
$$

The second difference is that while the evaluations of the first layer $p_0$ happen in a coset, further evaluations happen in the original (blown up) evaluation domain (which is avoided for the first polynomial as it might lead to divisions by zero with the polynomials used in the Starknet STARK protocol). To do this, the prover defines the first reduced polynomial as:

$$
p_{1}(x) = 2(g_{0}(9x^2) + \zeta_0 \frac{h_{0}(9x^2)}{x})
$$

Notice that the prover has also divided by $x$ instead of $3x$. This is a minor change that helps with how the verifier code is structured.

This means that the verifier computes the queries on $p_1{x}$ at points on the original subgroup. So the queries of the first layer are produced using $v' = v/3$ (assuming no skipped layers).

$$
p_1((v'^2) = p_0(v) + p_0(-v) + \zeta_0 \cdot \frac{p_0(v) - p_0(-v)}{v'}
$$

<aside class="note">we assume no skipped layers, which is always the case in this specification for the first layer's reduction.</aside>

After that, everything happens as normal (except that now the prover uses the original evaluation domain instead of a coset to evaluate and commit to the layer polynomials).

Note that these changes can easily be generalized to work when layers are skipped.

## External Dependencies

In this section we list all dependencies and the API this standard relies on.

### Hash Functions

We rely on two type of hash functions:

* A circuit-friendly hash. Specifically, **Poseidon**.
* A standard hash function. Specifically, **Keccak**.

TODO: why the alternate use of hash functions?

### Channel

See the [Channel](channel.html) specification for more details.

### Evaluation of the first FRI layer

As part of the protocol, the prover must provide a number of evaluations of the first layer polynomial $p_0$. This is abstracted in this specification as the function `eval_oods_polynomial` which acts as an oracle from FRI's perspective.

TODO: not a very satisfying explanation

Note that this function is not fixed here, as the polynomial being "tested" could be computed in different ways. See the [Starknet STARK verifier specification](stark.html) for a concrete example (and for an explanation of why the function is named this way).

## Constants

We use the following constants throughout the protocol.

### Protocol constants

**`STARKNET_PRIME = 3618502788666131213697322783095070105623107215331596699973092056135872020481`**. The Starknet prime ($2^{251} + 17 \cdot 2^{192} + 1$).

**`FIELD_GENERATOR = 3`**. The generator for the main multiplicative subgroup of the Starknet field. This is also used as coset factor to produce the coset used in the first layer's evaluation.

### FRI constants

**`MAX_LAST_LAYER_LOG_DEGREE_BOUND = 15`**. TKTK

**`MAX_FRI_LAYERS = 15`**. The maximum number of layers in the FRI protocol. This means that the protocol can test that committed polynomials exist and are of degree at most $2^{15}$. (TODO: double check)

**`MAX_FRI_STEP = 4`**. The maximum number of layers that can be skipped in FRI (see the overview for more details).

**`MONTGOMERY_R = 3618502788666127798953978732740734578953660990361066340291730267701097005025`**. The Montgomery form of $2^{256} \mod \text{STARK_PRIME}$:

### TODO: Step generators

* we are in a coset, so a fixed value `g=3` is chosen
* we also must understand how to compute the skipped layers, that is what are the elements of the subgroups of order $2^i$ for $i$ in $[1, 2, 3, 4]$ used by the prover and what are their corresponding inverses.

These are used to skip layers during the FRI protocol. Only 1, 2, 3, or 4 layers can be skipped, each associated to one of the constant below (except for skipping a single layer which is trivial):

```rust
// to skip 4 layers
const OMEGA_16: felt252 = 0x5c3ed0c6f6ac6dd647c9ba3e4721c1eb14011ea3d174c52d7981c5b8145aa75;
// to skip 3 layers
const OMEGA_8: felt252 = 0x446ed3ce295dda2b5ea677394813e6eab8bfbc55397aacac8e6df6f4bc9ca34;
// to skip 2 layers
const OMEGA_4: felt252 = 0x1dafdc6d65d66b5accedf99bcd607383ad971a9537cdf25d59e99d90becc81e;
```

TODO: explain more here

## Configuration

### General configuration

The FRI protocol is globally parameterized according to the following variables which from the protocol making use of FRI. For a real-world example, check the [Starknet STARK verifier specification](stark.md).

**`n_verifier_friendly_commitment_layers`**. The number of layers (starting from the bottom) that make use of the circuit-friendly hash.

**`proof_of_work_bits`**. The number of bits required for the proof of work. This value should be between 20 and 50.

### Commitment configuration

The protocol as implemented accepts proofs created using different parameters. This allows provers to decide on the trade-offs between proof size, prover time and space complexity, and verifier time and space complexity. 

A FRI layer reduction can be configured with the following fields:

**`table_n_columns`**. The number of values committed in each leaf of the Merkle tree. As explained in the overview, each FRI reduction makes predictible related queries to each layer, as such related points are grouped together to reduce multiple related queries to a single one.

**`vector_height`**. The height of the Merkle tree. See the FRI config below to understand how this is validated. (TODO: why do we carry this if we already know the domain size there?)

**`vector_n_verifier_friendly_commitment_layers`**. The number of layers (starting from the bottom) that use a circuit-friendly hash (TODO: double check). (TODO: remove this level of detail? maybe not if this has to match the proof format)

```rust
struct VectorCommitmentConfig {
    height: felt252,
    n_verifier_friendly_commitment_layers: felt252,
}

struct TableCommitmentConfig {
    n_columns: felt252,
    vector: VectorCommitmentConfig,
}
```

### FRI configuration

A FRI configuration contains the following fields:

**`log_input_size`**. The size of the input layer to FRI (the number of evaluations committed). (TODO: double check)

**`n_layers`**. The number of layers or folding that will occur as part of the FRI proof.

**`inner_layers`**. The configuration for each of the layers (minus the first layer).

**`fri_step_sizes`**. The number of layers to skip for each folding/reduction of the protocol.

**`log_last_layer_degree_bound`**. The degree of the last layer's polynomial. As it is sent in clear as part of the FRI protocol, this value represents the (log) number of coefficients (minus 1) that the proof will contain.

```rust
struct FriConfig {
    log_input_size: felt252,
    n_layers: felt252,
    inner_layers: Span<TableCommitmentConfig>,
    fri_step_sizes: Span<felt252>,
    log_last_layer_degree_bound: felt252,
}
```

TODO: validate(cfg, log_n_cosets, n_verified_friendly_commitment_layers):

* the number of layers `n_layers` must be within the range `[2, MAX_FRI_LAYERS]` (see constants)
* the `log_last_layer_degree_bound` must be less or equal to `MAX_LAST_LAYER_LOG_DEGREE_BOUND`
* the first`fri_step_sizes[0]` must be 0 (TODO: explain why)
* for every `fri_step_sizes[i]` check:
  * that the step `fri_step_sizes[i]` is within the range `[1, MAX_FRI_STEP]`
  * that the previous layer table commitment configuration `inner_Layers[i-1]` has
    * a number of columns `n_columns = 2^fri_step` (TODO: why?)
    * a valid configuration, which can be verified using the expected log input size and the `n_verifier_friendly_commitment_layers`
      * expected log input size should be the input size minus all the step sizes so far
* the `log_expected_input_degree + log_n_cosets == log_input_size`
  * TODO: why is log_n_cosets passed? and what is it? (number of additional cosets with the blowup factor?)
  * where `log_expected_input_degree = sum_of_step_sizes + log_last_layer_degree_bound`

## Commitments

Commitments of polynomials are done using [Merkle trees](). The Merkle trees can be configured to hash some parameterized number of the lower layers using a circuit-friendly hash function (Poseidon).

* TODO: why montgomery form?

### Table commitments

A table commitment in this context is a vector commitment where leaves are potentially hashes of several values (tables of multiple columns and a single row).

### Vector commitments

A vector commitment is simply a Merkle tree. 

TODO: diagram.

![vector commit](/img/starknet/fri/vector_commit.png)

### Vector membership proofs

A vector decommitment/membership proof must provide a witness (the neighbor nodes missing to compute the root of the Merkle tree) ordered in a specific way. The following algorithm dictates in which order the nodes hash values provided in the proof are consumed:

![vector decommit](/img/starknet/fri/vector_decommit.png)

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

## Protocol

The FRI protocol is split into two phases:

1. Commit phase
2. Query phase

### Commit Phase

This should basically just absorb the commitments of every layer sent by the prover (potentially skipping layers)

```rust
#[derive(Drop, Copy, PartialEq, Serde)]
struct TableCommitmentConfig {
    n_columns: felt252, // TODO: gets divided by 2 at every step in FRI?
    vector: VectorCommitmentConfig,
}
struct VectorCommitmentConfig {
    height: felt252, // TODO: ?
    n_verifier_friendly_commitment_layers: felt252, // TODO: ?
}
```

The layer 0 polynomial is not part of the protocol, we assume that it comes from somewhere and that we can query evaluations of it in a coset $3 \cdot \omega_e$ where $\omega_e$ is the generator of the evaluation domain. In the [Starknet STARK protocol](stark.html) it represents a blown up evaluation domain, that is, an evaluation domain that is a larger power of 2 than the evaluation domain used in the protocol.

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

We process it in the following way:

1. Enforce that the first layer has a step size of 0 (`cfg.fri_step_sizes[0] == 0`). (Note that this is mostly to make sure that the prover is following the protocol correctly, as the second layer is never skipped in this standard.)
1. Go through each commitment in order in the `inner_layers` field and perform the following:
   1. Absorb the commitment using the channel.
   1. Produce a random challenge.
1. Absorb the `last_layer_coefficients` with the channel.
1. Check that the last layer's degree is correct (according to the configuration `log_last_layer_degree_bound`, see the [Configuration section](#configuration)): `2^cfg.log_last_layer_degree_bound == len(unsent_commitment.last_layer_coefficients)`.
1. return all the random challenges.

### Query Phase

FRI queries are generated once, and then refined through each reduction of the FRI protocol. The number of queries that is randomly generated is based on [configuration]().

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

Or in terms of commitment, that the decommitment at path the path behind `index` is `y_value`.

<aside class="note">This is not exactly correct. The Commitment section explains that `index` points to a point, whereas we need to point to the path in the Merkle tree commitment that gathers its associated points. In addition, `y_value` only gives one evaluation, so the prover will need to witness associated evaluations surrounding the `y_value` as well (see Table Commitment section).</aside>

#### Generating The First Queries

The generation of each FRI query goes through the same process:

* Sample a random challenge from the [channel]().
* Truncate the challenge to obtain the lower 128-bit chunk.
* Reduce it modulo the size of the evaluation domain.

Finally, when all FRI queries have been generated, they are sorted in ascending order.

TODO: this is important due to the decommit algorithm.

#### Converting A Query To An Evaluation Point

A query $q$ (a value within $[0, 2^{n_e}]$ for $n_e$ the log-size of the blown-up evaluation domain) can be converted to an evaluation point in the following way.

First, compute the bit-reversed exponent:

$$
q' = \text{bit_reverse}(q \cdot 2^{64 - n_e})
$$

Then compute the element of the blown-up evaluation domain in the coset (with $\omega_e$ the generator of the evaluation domain):

$$
3 \cdot \omega_e^{q'}
$$

TODO: explain why not just do $3 \cdot \omega_e{q}$

#### Verify A Layer's Query

TODO: refer to the section on the first layer evaluation stuff (external dependency)

Besides the first and last layers, each layer verification of a query happens by simply decommiting a layer's queries.

```rust
table_decommit(commitment, paths, leaves_values, witness, settings);
```

TODO: As explained in the section on Merkle Tree Decommitment, witness leaves values have to be given as well.

TODO: link to section on merkle tree

#### Computing the next layer's queries

Each reduction will produce queries to the next layer, which will expect specific evaluations.

The next queries are derived as:

* index: index / coset_size
* point: point^coset_size
* value: FRI formula below

where coset_size is 2, 4, 8, or 16 depending on the layer (but always 2 for the first layer).

TODO: explain the relation between coset_size and the step size. coset_size = 2^step_size

##### FRI formula

The next evaluations expected at the queried layers are derived as:

Queries between layers verify that the next layer $p_{i+j}$ is computed correctly based on the currently layer $p_{i}$.
The next layer is either the direct next layer $p_{i+1}$ or a layer further away if the configuration allows layers to be skipped.
Specifically, each reduction is allowed to skip 0, 1, 2, or 3 layers (see the `MAX_FRI_STEP` constant).

TODO: why MAX_FRI_STEP=3?

no skipping:

* given a layer evaluations at $\pm v$, a query without skipping layers work this way:
* we can compute the next layer's *expected* evaluation at $v^2$ by computing $p_{i+1}(v^2) = \frac{p_{i}(v)+p_{i}(-v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-v)}{2v}$
* we can then ask the prover to open the next layer's polynomial at that point and verify that it matches

1 skipping with $\omega_4$ the generator of the 4-th roots of unity (such that $\omega_4^2 = -1$):

* $p_{i+1}(v^2) = \frac{p_{i}(v)+p_{i}(-v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-v)}{2v}$
* $p_{i+1}(-v^2) = \frac{p_{i}(\omega_4 v)+p_{i}(-\omega_4 v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-\omega_4 v)}{2 \cdot \omega_4 \cdot v}$
* $p_{i+2}(v^4) = \frac{p_{i+1}(v^2)+p_{i+1}(-v^2)}{2} + \zeta_i^2 \cdot \frac{p_i(v^2) - p_i(-v^2)}{2 \cdot v^2}$

as you can see, this requires 4 evaluations of p_{i} at $v$, $-v$, $\omega_4 v$, $-\omega_4 v$.

2 skippings with $\omega_8$ the generator of the 8-th roots of unity (such that $\omega_8^2 = \omega_4$ and $\omega_8^4 = -1$):

* $p_{i+1}(v^2) = \frac{p_{i}(v)+p_{i}(-v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-v)}{2v}$
* $p_{i+1}(-v^2) = \frac{p_{i}(\omega_4 v)+p_{i}(-\omega_4 v)}{2} + \zeta_i \cdot \frac{p_i(v) - p_i(-\omega_4 v)}{2 \cdot \omega_4 \cdot v}$
* $p_{i+1}(\omega_4 v^2) = \frac{p_{i}(\omega_8 v)+p_{i}(- \omega_8 v)}{2} + \zeta_i \cdot \frac{p_i(\omega_8 v) - p_i(- \omega_8 v)}{2 \omega_8 v}$
* $p_{i+1}(-\omega_4 v^2) = \frac{p_{i}(\omega_8^3 v)+p_{i}(- \omega_8^3 v)}{2} + \zeta_i \cdot \frac{p_i(\omega_8^3 v) - p_i(-\omega_8^3 v)}{2 \cdot \omega_8^3 \cdot v}$
* $p_{i+2}(v^4) = \frac{p_{i+1}(v^2)+p_{i+1}(-v^2)}{2} + \zeta_i^2 \cdot \frac{p_{i+1}(v^2) - p_{i+1}(-v^2)}{2 \cdot v^2}$
* $p_{i+2}(-v^4) = \frac{p_{i+1}(\omega_4 v^2)+p_{i+1}(-\omega_4v^2)}{2} + \zeta_i^2 \cdot \frac{p_{i+1}(\omega_4 v^2) - p_{i+1}(-\omega_4 v^2)}{2 \cdot \omega_4 v^2}$
* $p_{i+3}(v^8) = \frac{p_{i+2}(v^4)+p_{i+2}(-v^4)}{2} + \zeta_i^4 \cdot \frac{p_{i+2}(v^4) - p_{i+2}(-v^4)}{2 \cdot v^4}$

as you can see, this requires 8 evaluations of p_{i} at $v$, $-v$, $\omega_4 v$, $-\omega_4 v$, $\omega_8 v$, $- \omega_8 v$, $\omega_8^3 v$, $- \omega_8^3 v$.

3 skippings with $\omega_{16}$ the generator of the 16-th roots of unity (such that $\omega_{16}^2 = \omega_{8}$, $\omega_{16}^4 = \omega_4$, and $\omega_{16}^8 = -1$):

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

as you can see, this requires 16 evaluations of p_{i} at $v$, $-v$, $\omega_4 v$, $-\omega_4 v$, $\omega_8 v$, $- \omega_8 v$, $\omega_8^3 v$, $- \omega_8^3 v$, $\omega_16 v$, $-\omega_16 v$, $\omega_16^3 v$, $-\omega_16^3 v$, $\omega_16^5 v$, $-\omega_16^5 v$, $\omega_7 v$, $-\omega_7 v$.

TODO: reconcile with section on the differences with vanilla FRI

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

**`fri_commit(channel, cfg)`**.

1. Take a channel with a prologue (See the [Channel](#channel) section). A prologue contains any context relevant to this proof.
1. Produce the FRI commits according to the [Commit Phase](#commit-phase) section.
2. Produce the proof of work according to the [Proof of Work](#proof-of-work) section.
3. Generate `n_queries` queries in the `eval_domain_size` according to the [Generating Queries](#generating-the-first-queries) section.
4. Convert the queries to evaluation points following the [Converting A Query To An Evaluation Point](#converting-a-query-to-an-evaluation-point) section, producing `points`.
5. Evaluate the first layer at the queried `points` using the external dependency (see [External Dependencies](#external-dependencies) section), producing `values`.
6. Produce the fri_decommitment as `FriDecommitment { values, points }`.

**`fri_verify_initial(queries, fri_commitment, decommitment)`**.

* enforce that the number of queries matches the number of values to decommit
* enforce that last layer has the right number of coefficients (TODO: how?)
* compute the first layer of queries `gather_first_layer_queries` as `FriLayerQuery { index, y_value, x_inv_value: 3 / x_value }` for each `x_value` and `y_value`
* initialize and return the two state objects

```rust
(
    FriVerificationStateConstant {
        n_layers: config.n_layers - 1,
        commitment: fri_commitment.inner_layers, // the commitments
        eval_points: fri_commitment.eval_points, // the challenges
        step_sizes: config.fri_step_sizes[1:], // the number of reduction at each steps
        last_layer_coefficients_hash: hash_array(last_layer_coefficients),
    },
    FriVerificationStateVariable { iter: 0, queries: fri_queries }
)
```

**`fri_verify_step(stateConstant, stateVariable, witness, settings)`**.

* enforce that `stateVariable.iter <= stateConstant.n_layers`
* compute the next layer queries (TODO: link to section on that)
* verify the queries
* increment the `iter` counter
* return the next queries and the counter

**`fri_verify_final(stateConstant, stateVariable, last_layer_coefficients)`**.

* enforce that the counter has reached the last layer from the constants (`iter == n_layers`)
* enforce that the last_layer_coefficient matches the hash contained in the state (TODO: only relevant if we created that hash in the first function)
* manually evaluate the last layer's polynomial at every query and check that it matches the expected evaluations.

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

TKTK

## Security Considerations

* number of queries?
* size of domain?
* proof of work stuff?

security bits: `n_queries * log_n_cosets + proof_of_work_bits`
