Run all tests and fix any failures in $ARGUMENTS.

Steps:

1. python3 -m pytest $ARGUMENTS -v
2. If failures: fix them, run again
3. Only stop when all tests pass
4. Show final output
