"""Block programs over one flow IR (ADR-0020): the IR, the catalogue, the linter and the views.

Offline only (MW1 / F1): nothing here sends input, reads packets or runs user text. The Python view
is PARSED with `ast` and never executed; the executor (later) runs only the IR.
"""
