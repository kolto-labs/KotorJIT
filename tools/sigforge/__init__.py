"""sigforge: Project-agnostic, instruction-aware binary signature synthesis engine.

Supports PE32/PE64, ELF32/ELF64, and Mach-O (x86, x86_64, ARM, ARM64):
- BinaryView: uniform section/VA mapping and fast multi-pattern byte search.
- Masker: Capstone-based relocation/branch masking preserving struct offsets.
- Synthesizer: shortest strictly-unique (count == 1) masked signatures,
  tail-jmp thunk xref signatures, field-offset extraction, and cross-build
  signature unification.
"""
from .binary_view import BinaryView, SectionView
from .masker import MaskedSignature, mask_instructions
from .synthesizer import (
    FieldExtraction,
    SignatureResult,
    extract_field_offset,
    synthesize_unique,
    unify_signatures,
)

__all__ = [
    "BinaryView",
    "FieldExtraction",
    "MaskedSignature",
    "SectionView",
    "SignatureResult",
    "extract_field_offset",
    "mask_instructions",
    "synthesize_unique",
    "unify_signatures",
]
