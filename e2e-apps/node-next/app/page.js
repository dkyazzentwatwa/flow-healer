export default function HomePage() {
  return (
    <section
      aria-labelledby="agent-brief-heading"
      style={{
        background:
          'linear-gradient(180deg, #f8f1e4 0%, #efe3cf 52%, #e5d4bd 100%)',
        minHeight: '100vh',
        padding: '3rem 1.5rem',
        color: '#3d3027',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          width: 'min(100%, 52rem)',
          backgroundColor: 'rgba(255, 251, 244, 0.78)',
          border: '1px solid rgba(125, 99, 76, 0.18)',
          borderRadius: '28px',
          boxShadow: '0 24px 60px rgba(94, 73, 52, 0.14)',
          padding: '2.75rem',
          backdropFilter: 'blur(2px)',
        }}
      >
        <div style={{ fontSize: '0.85rem', fontWeight: 700, letterSpacing: '0.12em' }}>
          Autonomous agent briefing
        </div>
        <h1
          id="agent-brief-heading"
          style={{ fontSize: '2.75rem', lineHeight: 1.1, margin: '0.9rem 0 1rem' }}
        >
          Artifact Proof Node R2
        </h1>
        <div style={{ maxWidth: '44rem', lineHeight: 1.75, fontSize: '1.05rem' }}>
          <p>
            AI autonomous GitHub agents help teams triage issues, prepare small
            repository changes, run validation, and report the result with
            evidence. They keep each pass focused by following a written task
            contract instead of improvising broad changes across the repo.
          </p>
          <p>
            An effective agent brief reads like a calm operations card: it
            points to the target surface, names the proof that needs to be
            captured, and reminds reviewers what success should look like once
            the browser check is complete.
          </p>
          <p>
            That rhythm gives maintainers a warmer handoff at the end of every
            run, because the patch, the validation result, and the captured
            evidence all arrive together in a format that is easy to review and
            easy to trust.
          </p>
        </div>
      </div>
    </section>
  );
}
