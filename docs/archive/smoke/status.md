# Status Smoke Note

Run `flow-healer status` to print a JSON status row for each managed repo. It shows current issue counts, whether healing is paused, and recent attempt activity so operators can quickly confirm queue health.
Treat unchanged issue counts as normal if the latest attempt timestamp is still moving forward between smoke checks.
