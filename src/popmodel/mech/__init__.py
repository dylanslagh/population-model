"""Phase 5: the mechanistic layer.

Selection and transmission on one side, a changing fertility environment on the
other, and the observed fertility path as the result of both rather than as an
input. Spec section 6 is the design; section 6.10, the anti-epicycle rule, is
the one that governs how it may be parameterised.

Read in this order: `parameters.py` for why nothing here is fitted,
`composition.py` for who is becoming more common, `environment.py` for what a
given disposition produces, and `engine.py` for the bookkeeping that puts them
together.
"""

from popmodel.mech import composition, engine, environment, parameters  # noqa: F401
from popmodel.mech.composition import (  # noqa: F401
    NamedGroup,
    TypeSystem,
    named_groups,
    toy_demonstration,
)
from popmodel.mech.environment import Environment  # noqa: F401
from popmodel.mech.engine import MechResult, project, step  # noqa: F401
from popmodel.mech.parameters import ParameterError, ParameterSet  # noqa: F401
