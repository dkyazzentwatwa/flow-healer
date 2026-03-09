const Health = () => {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <section
        aria-label="Application health status"
        className="w-full max-w-md rounded-xl border bg-card p-6 shadow-sm"
      >
        <p className="text-sm font-medium uppercase tracking-[0.2em] text-muted-foreground">
          System status
        </p>
        <div className="mt-4 flex items-center gap-3">
          <span className="h-3 w-3 rounded-full bg-green-500" aria-hidden="true" />
          <p className="text-2xl font-semibold text-foreground">Operational</p>
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          Prosper Chat is accepting requests and core services are responding normally.
        </p>
      </section>
    </div>
  );
};

export default Health;
