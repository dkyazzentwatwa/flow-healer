## 2025-05-15 - WAL mode optimization for SQLite
**Learning:** SQLite's default journal mode (DELETE) performs a synchronous disk write for every transaction, which can be a massive bottleneck in write-heavy workloads (like frequent locking/unlocking in a dispatcher). Enabling WAL (Write-Ahead Logging) and setting synchronous to NORMAL allows for much higher write throughput while maintaining safety.
**Action:** Always consider WAL mode for SQLite databases that experience frequent small writes or require better concurrency.
