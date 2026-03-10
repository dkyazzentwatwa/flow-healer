# Fix Path Ordering

Use these layers to order GitHub issues so issue numbers reflect the recommended repair path.

## Layers

### Layer 0

Broken imports, circular dependencies, missing exports, schema or type-system breaks.

### Layer 1

Core abstraction or boundary problems:

- wrong execution boundary
- repo-root escape
- broken state model
- unsafe interface contracts

### Layer 2

Cross-impact bugs:

- wrong validation routing
- queue starvation
- connector availability handling
- retry or requeue logic bugs

### Layer 3

Isolated bugs with mostly local blast radius.

### Layer 4

Performance problems after correctness is stable.

### Layer 5

Code quality and maintainability work:

- cleanup
- dead code
- naming
- passive observability improvements

### Layer 6

Tests and docs that should reflect the fixed state.

## Tie Breakers

- Order shared components before leaf components.
- Order parser or contract fixes before validation or execution fixes.
- Order store and lease correctness before loop behavior built on top of that state.
- Order issue-creation quality fixes after the underlying parser or routing bugs they depend on.
