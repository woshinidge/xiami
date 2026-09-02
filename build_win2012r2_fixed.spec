# -*- mode: python ; coding: utf-8 -*-

import os


# The Win2012 R2 release path historically carried a duplicate spec and drifted
# away from the canonical source policy. Execute the canonical spec so both
# normal builds and release builds use the same PYZ/resource rules.
canonical_spec = os.path.join(os.path.abspath(SPECPATH), "\u867e\u7c73\u5de5\u5177\u7bb1.spec")
with open(canonical_spec, "r", encoding="utf-8") as spec_file:
    exec(compile(spec_file.read(), canonical_spec, "exec"), globals(), globals())
