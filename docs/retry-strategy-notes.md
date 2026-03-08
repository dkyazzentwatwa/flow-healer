# Retry Strategy Notes

## Question

What is the better retry policy for GitHub mutation requests: fixed backoff or full-jitter backoff?

## Short answer

Use full-jitter exponential backoff for retryable GitHub mutation failures, while still honoring GitHub's explicit pacing headers and mutative-request guidance.

Fixed backoff is acceptable for a single low-volume worker, but it is a weaker default once multiple repos, workers, or retries can line up at the same time.

## Why this matters for GitHub mutations

GitHub explicitly recommends that integrations:

- avoid concurrent requests
- send mutative `POST`, `PATCH`, `PUT`, and `DELETE` requests serially
- pause at least one second between mutative requests
- respect `retry-after` and `x-ratelimit-reset`
- use exponentially increasing waits when secondary rate limits continue

That means the retry policy should optimize for two things at once:

1. staying polite to GitHub's secondary rate limits
2. avoiding synchronized retry spikes from our own workers

## Fixed backoff

Fixed backoff means every retry waits the same amount of time, such as 5 seconds.

### Strengths

- very simple to implement and reason about
- easy to explain in logs and incident reviews
- predictable upper bounds for operator-facing latency
- acceptable when there is only one worker and failures are rare

### Weaknesses

- multiple workers tend to retry in lockstep
- repeated collisions are more likely under rate limiting or shared outages
- it does not widen the retry interval as pressure continues
- it ignores GitHub's guidance to increase waits when secondary rate limits keep happening

### Best fit

Fixed backoff is mostly useful as a minimum pacing floor, not as the main retry algorithm.

## Full-jitter exponential backoff

Full jitter chooses a random sleep in the range `0..cap`, where `cap` grows exponentially by attempt and is bounded by a maximum.

Example:

```text
sleep = random(0, min(base * 2^attempt, max_backoff))
```

### Strengths

- spreads retries out so workers do not stampede GitHub at the same moment
- reduces repeated collision risk during shared transient failures
- matches GitHub's recommendation to increase wait times on continued secondary-rate-limit failures
- widely recommended for distributed clients because it lowers total retry work under contention

### Weaknesses

- less predictable per-attempt timing
- slightly harder to reproduce exactly from logs unless the chosen delay is recorded
- may feel slower on an individual lucky/unlucky retry even though system-wide behavior is healthier

### Best fit

Full jitter is the better default when more than one worker, repo, or queued mutation can be active over time.

## Tradeoff summary

| Option | Main benefit | Main risk | Operational effect |
| --- | --- | --- | --- |
| Fixed backoff | Simplicity and predictability | Retry synchronization and repeated collisions | Fine for one quiet worker, fragile under bursty contention |
| Full-jitter backoff | Better load spreading and lower herd behavior | Less deterministic timing | Safer default for distributed or queue-based GitHub automation |

## Recommendation for Flow Healer

For GitHub mutation retries, prefer this order of operations:

1. If GitHub returns `retry-after`, wait exactly that long.
2. If `x-ratelimit-remaining` is `0`, wait until `x-ratelimit-reset`.
3. Otherwise, for retryable transient failures, use capped exponential backoff with full jitter.
4. Keep mutation issuance serialized and preserve at least a one-second floor between successful mutative calls.
5. Stop after a small retry budget and surface the failure instead of stretching the queue indefinitely.

## Suggested policy shape

- base delay: 1 second
- growth: exponential by attempt
- jitter: full jitter over the current cap
- cap: 30 to 60 seconds for normal mutation retries
- retry budget: small, such as 3 to 5 attempts depending on failure class

## Practical interpretation

The recommendation is not "randomize everything." The recommendation is:

- use deterministic waits when GitHub tells us exactly how long to wait
- use a fixed minimum pacing floor for normal mutation traffic
- use full-jitter exponential backoff only for retry timing when failures are transient and GitHub has not already given a precise delay

That hybrid approach keeps the system compliant with GitHub guidance and avoids self-inflicted retry waves.

## Sources

- GitHub REST API best practices: https://docs.github.com/rest/guides/best-practices-for-integrators
- GitHub REST API rate limits: https://docs.github.com/en/enterprise-cloud@latest/rest/using-the-rest-api/rate-limits-for-the-rest-api
- AWS Architecture Blog, "Exponential Backoff and Jitter": https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Google Cloud retry strategy guidance: https://cloud.google.com/iam/docs/retry-strategy
