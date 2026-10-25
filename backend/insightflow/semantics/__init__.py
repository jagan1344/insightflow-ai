"""Schema-grounded semantic layer: typed question spec, semantic type checks,
and semantic-preservation verification (spec vs SQL vs rows vs response)."""
from .spec import SemanticSpec, build_spec, requested_shape        # noqa: F401
from .typecheck import typecheck                                   # noqa: F401
from .preserve import preserve, SemanticFinding                    # noqa: F401
from .verify import verify_semantics, SemanticReport               # noqa: F401
