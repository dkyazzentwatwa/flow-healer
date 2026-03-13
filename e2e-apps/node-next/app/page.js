export default function HomePage() {
  return (
    <section
      aria-labelledby="todo-routes-heading"
      style={{
        backgroundColor: '#f2e6d8',
        minHeight: '100vh',
        padding: '3rem 2rem',
        color: '#2f241d',
      }}
    >
      <div style={{ fontSize: '0.95rem', fontWeight: 600, letterSpacing: '0.08em' }}>
        Browser smoke ready
      </div>
      <h1
        id="todo-routes-heading"
        style={{ fontSize: '2.5rem', margin: '1rem 0 0.5rem' }}
      >
        Artifact Proof E3
      </h1>
      <div style={{ maxWidth: '48rem', lineHeight: 1.7 }}>
        <p>
          AI autonomous GitHub agents are software workers that inspect
          repositories, propose changes, run validation, and report results back
          on GitHub. They usually start from an issue or task contract, gather
          the local context they need, and prepare a narrow fix instead of
          making broad repo changes.
        </p>
        <p>
          A typical run follows the same loop each time: read the target files,
          update the implementation, execute the required checks, and capture
          evidence such as logs or screenshots when the task asks for browser
          proof. That keeps the workflow understandable for reviewers because
          each step is tied to a clear instruction and a concrete output.
        </p>
        <p>
          This approach is useful because teams get faster issue handling
          without losing control of quality. People can review a small patch,
          see what validation passed, and merge with more confidence when the
          agent leaves behind readable summaries and repeatable artifacts.
        </p>
      </div>
    </section>
  );
}
