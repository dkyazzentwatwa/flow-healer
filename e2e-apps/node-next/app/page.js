export default function HomePage() {
  return (
    <section aria-labelledby="todo-routes-heading">
      <h2 id="todo-routes-heading">Available todo routes</h2>
      <ul>
        <li>GET /api/todos</li>
        <li>POST /api/todos</li>
        <li>POST /api/todos/:id/complete</li>
      </ul>
    </section>
  );
}
