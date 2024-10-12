---
title: "starknet FRI"
abstract: "<p>The <strong>Fast Reed-Solomon Interactive Oracle Proofs of Proximity (FRI)</strong> is a cryptographic protocol that allows a prover to prove to a verifier (in an interactive, or non-interactive fashion) that a hash-based commitment (e.g. a Merkle tree) of a vector of values represent the evaluations of a polynomial of some known degree. (That is, the vector committed is not just a bunch of uncorrelated values.) The algorithm is often referred to as a \"low degree\" test, as the degree of the underlying polynomial is expected to be much lower than the degree of the field the polynomial is defined over. Furthermore, the algorithm can also be used to prove the evaluation of a committed polynomial, an application that is often called FRI-PCS. We discuss both algorithms in this document, as well as how to batch multiple instances of the two algorithms.</p>

<p>For more information about the original construction, see <a href=\"https://eccc.weizmann.ac.il/report/2017/134/\">Fast Reed-Solomon Interactive Oracle Proofs of Proximity</a>. This document is about the specific instantiation of FRI and FRI-PCS as used by the StarkNet protocol.</p>

<aside class=\"note\">Specifically, it matches the [integrity verifier](https://github.com/HerodotusDev/integrity/tree/main/src) which is a Cairo implementation of a Cairo verifier. There might be important differences with the Cairo verifier implemented in C++ or Solidity.</aside>"
sotd: "none"
---

## Overview of FRI and FRI-PCS

```py
# FRI
# ---
#
# We follow the ethSTARK paper (https://eprint.iacr.org/2021/582) 
#
# 
# Setup
# =====
#
# We use the starknet field (https://docs.starknet.io/architecture-and-concepts/cryptography/p-value/)
#

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

#
# How are polynomials split in two in FRI?
# ========================================
#

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

#
# FRI reduction example
# =====================
# Here's the commit phase of FRI (without the actual commitments)
#

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

#
# FRI query examples
# ==================
# Let's look at what the verifier would have to check at the end.
#

# first round/reduction
v = 392 # <--------------------------------------- fake sample a point
p0_v, p0_v_neg = p0(v), p0(-v) # <--------------- the 2 queries we need
g0_square = (p0_v + p0_v_neg)/2
h0_square = (p0_v - p0_v_neg)/(2 * v)
assert p0_v == g0_square + v * h0_square # <------ sanity check
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


#
# skipping FRI layers optimization
# ================================
# section 3.11.1 "Skipping FRI Layers" of the ethSTARK paper describes an optimization which skips some of the layers/rounds.
# unfortunately they don't describe much on how to achieve this, 
# but "A summary on the FRI low degree test" (https://eprint.iacr.org/2022/1216.pdf) has more detail.
#
# The intuition is the following: if we removed the first round commitment (to the polynomial p1), 
# then the verifier would not be able to:
#
# - query p1(v^2) to verify that layer
# - query p1(-v^2) to continue the protocol and get g1, h1
#
# The first point is fine, as there's nothing to check the correctness of.
# To address the second point, we can use the same technique we use to compute p1(v^2).
# Remember, we needed p0(v) and p0(-v) to compute g0(v^2) and h0(v^2).
# But to compute g0(-v^2) and h0(-v^2), we need the quadratic residues of -v^2,
# that is w, such that w^2 = -v^2,
# so that we can compute g0(-v^2) and h0(-v^2) from p0(w) and p0(-w).
#
# We can easily compute them by using tau, the generator of the subgroup of order 4

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

# note that there is no point producing a new challenge zeta1 as nothing more was observed from the verifier's point of view during the skipped round.
# as such, FRI implementations will usually use zeta0^2 as "folding factor"
# (and so on if more folding occurs)

# 
# Last layer optimization
# =======================
# section 3.11.2 "FRI Last Layer" of the ethSTARK paper describes an optimization which stops at an earlier round. 
# We show this here by removing the last round.
#

# at the end of the second round we imagine that the verifier receives the coefficients of p2 (h2 and g2) directly
p2_v = h2 + v^4 * g2 # they can then compute p2(v^4) directly
assert g1_square + zeta1 * h1_square == p2_v # and then check correctness

#
# How would commitments work?
# ===========================
#

# if we evaluate the polynomial on a set of size 8 (so the blowup factor is 1)
g = find_gen2(log(8,2))

# we use a coset (e.g. 2 * g^i) to evaluate the polynomial at the different points
# (as otherwise we can't compute some of the rational polynomials)
# (the DEEP polynomial of the ethSTARK protocol might divide by zero)
coset = [2 * g^i for i in range(8)] 
poly8_evals = [p0(x) for x in coset] # <-- we would merklelify this as statement
```

### Overview of FRI-PCS

Given a polynomial $f$ and an evaluation point $a$, a prover who wants to prove that $f(a) = b$ can prove the related statement for some quotient polynomial $q$ of degree $deg(f) - 1$:

$$
\frac{f(x) - b}{x-a} = q(x)
$$

(This is because if $f(a) = b$ then $a$ should be a root of $f(x) - b$ and thus the polynomial can be factored in this way.)

Specifically, FRI-PCS proves that they can produce such a (commitment to a) polynomial $q$.

### Overview of aggregating multiple FRI proofs.

To prove that two polynomials $a$ and $b$ exist and are of degree at most $d$, a prove simply prove that a random linear combination of $a$ and $b$ exists and is of degree at most $d$.

TODO: what if the different polynomials are of different degrees?

### Notable differences with vanilla FRI

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

This shouldn't impact the protocol as we are just scaling with constants, but the verifier has to modify their queries slightly by not dividing by 2:

$$
p_{i+1}(v^2) = p_{i}(v) + p_{i}(-v) + \zeta_{i} g \cdot \frac{p_{i}(v) - p_{i}(-v)}{v}
$$

The second difference is that while the evaluations of the first layer $p_0$ happen in a coset, further evaluations happen in the original evaluation domain (which is avoided for the first polynomial as it might lead to divisions by zero with the polynomials used in the Starknet STARK protocol). To do this, the verifier removes the multiplication with the fixed element $g$ (as an evaluated point $v$ can be written $g \cdot v'$ for $v'$ in our original domain):

$$
p_{1}(v^2) = p_{0}(v) + p_{0}(-v) + \zeta_{0} \cdot g \cdot \frac{p_{0}(v) - p_{0}(-v)}{v}
$$

On their side, the prover has to use the challenge $\zeta_{0} / g$ instead of $\zeta_{0}$ when folding the polynomial:

$$
p_{1}(x) = g_{0}(x^2) + \frac{\zeta_{0}}{g} \cdot h_{0}(x^2)
$$

Then both side compute the next layer's queries for $p_1$ as $(v/g)^2$ (assuming no skipped layers, again). After that, everything happens as normal (except that now the prover uses the original evaluation domain instead of a coset to evaluate and commit to the layer polynomials).

Note that these changes can easily be generalized to work when layers are skipped.

## Dependencies

* Poseidon
* other hash function

## Constants

TODO: field + generator from STARK spec

We use the following constants throughout the protocol:

**`MAX_LAST_LAYER_LOG_DEGREE_BOUND = 15`**. TKTK

**`MAX_FRI_LAYERS = 15`**. The maximum number of layers in the FRI protocol. This means that the protocol can test that committed polynomials exist and are of degree at most $2^{15}$. (TODO: double check)

**`MAX_FRI_STEP = 4`**. The maximum number of layers that can be skipped in FRI (see the overview for more details).

### TODO: Step generators

These are used to skip layers during the FRI protocol. Only 1, 2, 3, or 4 layers can be skipped, each associated to one of the constant below (except for skipping a single layer which is trivial):

```rust
// to skip 4 layers
const OMEGA_16: felt252 = 0x5c3ed0c6f6ac6dd647c9ba3e4721c1eb14011ea3d174c52d7981c5b8145aa75;
// to skip 3 layers
const OMEGA_8: felt252 = 0x446ed3ce295dda2b5ea677394813e6eab8bfbc55397aacac8e6df6f4bc9ca34;
// to skip 2 layers
const OMEGA_4: felt252 = 0x1dafdc6d65d66b5accedf99bcd607383ad971a9537cdf25d59e99d90becc81e;
```

## Dynamic Configurations

The protocol as implemented accepts proofs created using different parameters. This allows provers to decide on the trade-offs between proof size, prover time and space complexity, and verifier time and space complexity. 

A FRI layer reduction can be configured with the following fields:

**`n_columns`**. The number of values committed in each leaf of the Merkle tree. As explained in the overview, each FRI reduction makes predictible related queries to each layer, as such related points are grouped together to reduce multiple related queries to a single one.

**`vector_height`**. The height of the Merkle tree (TODO: why do we carry this if we already know the domain size there?)

**`n_verifier_friendly_commitment_layers`**. The number of layers (starting from the bottom) that use a circuit-friendly hash (TODO: double check).

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
* the first`fri_step_sizes[0]` must be 0
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

Commitments of polynomials are done using [Merkle trees](). The merkle trees can be configured to hash some parameterized number of the lower layers using a circuit-friendly hash function (Poseidon).

* TODO: why montgomery form?

### Table commitments

A table commitment in this context is a vector commitment where leaves are potentially hashes of several values (tables of multiple columns and a single row).

### Vector commitments

A vector commitment is simply a Merkle tree. 

TODO: diagram.

![](/img/starknet/fri/vector_commit.png)

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

## Commit phase

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


```py
# TODO: step_sizes is ignored! Shouldn't we check that the layer cfg are properly following the step sizes?
def fri_commit_rounds(channel, n_layers, configs, unsent_commitments, step_sizes):
    commitments = []
    eval_points = []
    # TODO: we don't check that n_layers matches the length of these arrays!
    for unsent_commitment, cfg in zip(unsent_commitments, configs):
        commit = table_commit(channel, unsent_commitment, cfg) # absorbs the commitment # TODO: where is each cfg checked?
        commitments.append(commit)
        eval_points.append(channel.random_felt_to_prover())

def fri_commit(channel, unsent_commitment, cfg):
    assert cfg.fri_step_sizes[0] == 0

    # why n_layers - 1 ?
    commitments, eval_points = fri_commit_rounds(channel, cfg.n_layers-1, cfg.inner_layers, unsent_commitment.inner_layers, cfg.fri_step_sizes)

    # absorb last layer
    channel.read_felt_vector_from_prover(unsent_commitment.last_layer_coefficients)

    # check that the last layer matches the config
    assert pow(2, cfg.log_last_layer_degree_bound) == len(unsent_commitment.last_layer_coefficients)

    return FriCommitment(cfg, inner_layers=commitments, eval_points, last_layer_coefficients=unsent_commitment.last_layer_coefficients)
```

it seems like only the first round has a step size of 0, every other round has a step in `[1, MAX_FRI_STEP=4]`

## Queries

```rust
struct FriLayerComputationParams {
    coset_size: felt252,
    fri_group: Span<felt252>,
    eval_point: felt252,
}

#[derive(Drop, Copy, PartialEq, Serde)]
struct FriLayerQuery {
    index: felt252,
    y_value: felt252, // the evaluation on the last layer
    x_inv_value: felt252, // weirdly, we evaluate the last layer with 1/x^inv
}
```

```py
FIELD_GENERATOR = 3
FIELD_GENERATOR_INVERSE = 1206167596222043737899107594365023368541035738443865566657697352045290673494 # 3^-1

def generate_queries(channel, n_samples=cfg.n_queries, query_upper_bound=stark_domains.eval_domain_size):
    # sample
    samples = []
    assert query_upper_bound != 0
    for _ in range(n_samples):
        res = channel.random_felt_to_prover()
        low128 = res.low
        let _, sample = div_rem(low128, query_upper_bound) # low128 % eval_domain_size ?
        samples.append(sample)

    # sort and remove duplicates
    res = []
    sorted = merge_sort(samples)
    for i in range(1, len(sorted)):
        curr = sorted[i]
        if curr != prev:
            res.append(curr)
            prev = curr

    return res

def queries_to_points(queries, stark_domains):
    points = []
    assert stark_domains.log_eval_domain_size <= 64
    shift = pow(2, 64 - stark_domains.log_eval_domain_size) # shift is just 2^(64-i) ? how does it change through layers?
    for query in queries:
        idx = query * shift
        point = FIELD_GENERATOR * pow(stark_domains.eval_generator, idx.bit_reverse()) # TODO: ?
        points.append(point)

def gather_first_layer_queries(queries, evaluations, x_values):
    fri_queries = []
    for query, evaluation, x_value in zip(queries, evaluations, x_values):
        shifted_x_value = x_value * FIELD_GENERATOR_INVERSE # x / g (TODO: why?)
        fri_queries.append(FriLayerQuery(index=query.index, y_value=evaluation, x_inv_value=1/shifted_x_value))
    return fri_queries

def compute_coset_elements(queries, sibling_witness, coset_size, coset_start_index, fri_group):
    coset_elements = []
    coset_x_inv = 0
    for i in range(coset_size):
        if len(queries) > 0 and queries[0].index == coset_start_index + i:
            query = queries.remove(0)
            coset_elements.append(query.y_value)
            coset_x_inv = query.x_inv_value * fri_group[i] # TODO: are elements of the FRI group used to create coset?
        else:
            coset_elements.append(sibling_witness.remove(0))

    return coset_elements, coset_x_inv
        

# this seems to group queries by coset
def compute_next_layer(queries, sibling_witness, params):
    verify_indices = [] # coset used (its start index) for the query
    verify_y_values = [] # all the evaluations queried in each coset
    next_queries = [] # TODO: ?
    while len(queries) != 0:
        # defer verification of the query
        coset_index = queries[0].index // params.coset_size
        verify_indices.append(coset_index) # TODO: for merkle tree?

        # compute coset element (TODO: what?)
        coset_start_idx = coset_index * params.coset_size
        coset_elements, coset_x_inv = compute_coset_elements(query, sibling_witness, params.coset_size, coset_start_idx, params.fri_group)

        # at least one query was consumed (TODO: what?)
        assert len(coset_elements) > 0

        # defer verification of the y values (TODO: what?)
        verify_y_values.extend(coset_elements)

        # TODO: what?
        fri_formula_res = fri_formula(coset_elements_span, params.eval_point, coset_x_inv, params.coset_size)

        # TODO: what?
        next_x_inv = coset_x_inv ** params.coset_size
        next_queries.append(FriLayerQuery(index=coset_index, y_value=fri_formula_res, x_inv_value=next_x_inv))

    return next_queries, verify_indices, verify_y_values

def verify_last_layer(queries, poly):
        for query in queries:
            assert poly.eval(1/query.x_inv_value) == query.y_value

def get_fri_group():
    return [
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

def fri_verify_layer_step(queries, step_size, eval_point, commitment, layer_witness, settings):
    fri_group = get_fri_group()
    coset_size = 2**step_size # TODO: woot?
    params = FriLayerComputationParams(coset_size, fri_group, eval_point)

    # compute the next layer
    next_queries, verify_indices, verify_y_values = compute_next_layer(queries, layer_witness.leaves, params)

    # verify stuff(TODO: what?)
    table_decommit(commitment, verify_indices, TableDecommitment(values=verify_y_values), layer_witness.table_witness, settings)

    return next_queries
```

### How queries are generated

* in generate_queries():
  * each query is a 128-bit random value obtained by truncating the value sampled from F-S    
  * it is then reduced to `log_eval_domain_size` bits (which is enforced to be strictely less than 64 bits)
* in queries_to_points():
  * it is then shifted to the left to make it a 64-bit value: `a = query * 2^(64 - stark_domains.log_eval_domain_size`
  * it is then used to generate a point in the coset `3 * stark_domains.eval_generator^(a.bit_reverse())` (TODO: not sure why they bit reverse here, I think it's not necessary?)
  * TODO: but how come this can point to something that can be corrected with the fri_group... where does it get inverted also?

then:

* fri_first_layer::gather_first_layer_queries(queries, evaluations, x_values)
  * called with queries, decommitment.values, decommitment.points
    * where decommitment.values = oods_poly_evals and points is the return value of `query_to_points` above
  * FriLayerQuery with `index=queries[i], y_value=evaluations[i], x_inv_value = 3 / (x_values[i])`
  * so this cancels the earlier `3 *` that we had, and removes us from the coset?

TODO: how are x_values related to queries... wait WTF. Can I put the same x_values in EVERY query leaf?

then these are returned:

```rust
(
    FriVerificationStateConstant {
        n_layers: (commitment.config.n_layers - 1).try_into().unwrap(), // -1 due to the first layer missing
        commitment: commitment.inner_layers, // commitment of each poly (Except skipped layers)
        eval_points: commitment.eval_points, // same for challenges
        step_sizes: commitment
            .config
            .fri_step_sizes // step_sizes!
            .slice(1, commitment.config.fri_step_sizes.len() - 1),
        last_layer_coefficients_hash: hash_array(commitment.last_layer_coefficients), // hash of the last layer instead of commitment
    },
    FriVerificationStateVariable { 
        iter: 0, // iter 0 <-- used to know where to point to in the state above
        queries: fri_queries.span(),  // the fri queries calculated
    }
)
```

in subsequent queries, these two functions are called:

```py
# struct FriLayerQuery {
#    index: felt252,
#    y_value: felt252,
#    x_inv_value: felt252,
#}

# next_queries contains
# - the next (x, y_value) on the layer to double check (i.e. next_layer(x) = y)
# - it also gives coset_index as help on where to check (in the merkle tree?)
next_queries, verify_indices, verify_y_values = compute_next_layer(queries, layer_witness.leaves, params)

# why don't we use layer_witness.leaves??? -> they are contained in verify_y_values
# so this verifies that the evaluations we used are contained in the current layer's commitment, under the indices
table_decommit(commitment, verify_indices, verify_y_values, layer_witness.table_witness, settings)
retrun next_queries
```

### Queries verification

* Queries between layers verify that the next layer $p_{i+j}$ is computed correctly based on the currently layer $p_{i}$
* The next layer is either the direct next layer $p_{i+1}$ or a layer further away if the configuration allows layers to be skipped
* Specifically, each reduction is allowed to skip 1, 2, or 3 layers

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

> Note: in the implementation, the division by 2 does not happen, thus the other side of the checked identity must be multiplied by 2 (TODO: where does this happen?)

## Flow

throughout the flow it seems like a context object is passed (and mutated?):

```rust
#[derive(Drop, Serde)]
struct FriVerificationStateConstant {
    n_layers: u32,
    commitment: Span<TableCommitment>,
    eval_points: Span<felt252>,
    step_sizes: Span<felt252>,
    last_layer_coefficients_hash: felt252,
}
```

the three main functions are in `stark.cairo` and can be called successively, or called in a single call using the `verify()` function:

* stark.cairo
  * verify_initial -> this should return the initial set of queries
    * ...
    * stark_commit.cairo:stark_commit
      * ...
      * fri_commit
      * proof_of_work_commit
    * generate_queries
    * stark_verify.cairo:stark_verify
      * ...
      * fri.cairo:fri_verify_initial
        * gather_first_layer_queries

  * verify_step -> this should tkae a set of queries and return another set of queries
    * fri_verify_step
      * fri_verify_layer_step
        * compute_next_layer
        * table_decommit

  * verify_final(stateConstant, stateVariable, last_layer_coefficients)
    * fri.cairo:fri_verify_final
      * verify_last_layer

> WARNING: these functions only make sense when they are called sequentially with the right inputs! as such they should be used in a wrapper that keeps track of what the statement being proven is and what set of query it is associated to (otherwise you could just make up your queries)

initial (contained in verify_initial in the stark implementation):

1. start_commitment = stark_commit()
   1. this essentially contains the stark protocol (the start) and then...
   2. sample the `oods_alpha`, also called `interaction_after_oods` from the channel
   3. fri_commitment = fri_commit(channel, unsent_commitment.fri, cfg.fri) (TODO: where is cfg.fri validated?)
      1. assert cfg.fri_step_sizes[0] == 0
      2. commitments, eval_points = fri_commit_rounds()
         1. ?
      3. absorb the `unsent_commitment.last_layer_coefficients` in the channel
      4. check that `cfg.log_last_layer_degree_bound` is correctly set: `pow(2, cfg.log_last_layer_degree_bound) == len(coefficients)`
   4. proof_of_work_commit(channel, unsent_commitment.proof_of_work, cfg.proof_of_work)
2. last_layer_coefficients = stark_commitment.fri.last_layer_coefficients
3. queries = generate_queries(channel, cfg.n_queries, stark_domains.eval_domain_size)
4. con, var = stark_verify()
5. return con, var, last_layer_coefficients

step:

1. ?

final:

1. ?

### Test Vectors?

### Security Considerations

* number of queries?
* size of domain?

security bits: `n_queries * log_n_cosets + proof_of_work_bits`
