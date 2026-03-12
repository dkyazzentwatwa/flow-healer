export default function HomePage() {
  return (
    <section
      aria-labelledby="todo-routes-heading"
      style={{
        backgroundColor: '#39ff14',
        minHeight: '100vh',
        padding: '2rem',
      }}
    >
      <p>Browser smoke ready</p>
      <p>Artifact Proof E2</p>
      <h2 id="todo-routes-heading">Available todo routes</h2>
      <ul>
        <li>GET /api/todos</li>
        <li>POST /api/todos</li>
        <li>POST /api/todos/:id/complete</li>
      </ul>
    </section>
  );
}
