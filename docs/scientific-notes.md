# Scientific interpretation

BANC gives reconstructed structural connectivity. A graph-theoretic path is not
proof of a physiological route or a behavioral causal mechanism.

Minimum-hop mode assigns unit cost to each directed connection. Normalized-strength
mode uses `-log(max(count / post_count, epsilon))`, with natural logarithm and default
epsilon = 1e-12. Epsilon must be finite and in (0, 1]. Ratios are recomputed from the
public counts and original target input totals; the original rounded `norm` is also
preserved. Neither thresholding nor neuron exclusion renormalizes these totals.
Clamping prevents log(0); norm=1 has zero cost. The optimized product is a product
of epsilon-clamped structural contributions. `count / post_count` measures normalized
structural input contribution, not transmission probability. No model of neural
firing or neurotransmitter sign is implemented.

The library includes `1/log1p(count)` as an explicitly experimental raw-count cost
function, but exposes only the two documented modes in the CLI. A source equal to
its target yields a zero-hop, zero-cost path. Unreachable and unknown endpoints are
reported separately; no-path queries do not create successful result files.

Godot playback says "Illustrative path activation". v2/v3 comparisons
must identify the detector/table version and filtering. Static v888 data must not
be silently joined to live annotations or evidence from another version.

Selected-point EM displays JPEG-derived aligned-v0 imagery around a reconstructed
v888 SWC node. A skeleton sample is not a verified synapse location, and merely
seeing ultrastructure does not establish a connection or pathway. SWC provenance
and image alignment provenance remain separate. The public image MIP 0 used here
has 8 × 8 × 45 nm sampling; it is not described as lossless original EM. Neither
screen-space picking nor array-midpoint initialization estimates a biological soma.
