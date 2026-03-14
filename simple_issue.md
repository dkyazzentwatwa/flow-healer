Title: Add hello function returning "world"

## Required code outputs
- e2e-smoke/python/src/hello.py

## Input-only context
- (none)

## Validation
cd e2e-smoke/python && python -c "from src.hello import hello; assert hello() == 'world'"