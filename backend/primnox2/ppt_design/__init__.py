"""Design system for small-model PPT generation.

Two paths to slides:

1. Code path (SKILL.md): from primnox_docs import Deck; d.bullets(...); d.save()
   - 0.5B success: 35-40%
   - Flexible, requires code generation

2. Design path (this module): JSON routing through layout library
   - 0.5B success: 70-85% (target)
   - Deterministic, uses design tokens and locked rules
   - Router → Layout Library → Grid Engine → Renderer → PPTX

The design system never asks the model to "create" a design. It chooses from
proven patterns and applies deterministic rules for spacing, typography, color.
"""
