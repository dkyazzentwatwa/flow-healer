# frozen_string_literal: true

require "erb"

class DashboardController
  def show(request:, session_user:)
    if session_user.empty?
      return {
        status: 302,
        location: "/login",
        body: ""
      }
    end

    escaped_user = ERB::Util.html_escape(session_user)

    {
      status: 200,
      content_type: "text/html",
      body: <<~HTML
        <section style="min-height: 100vh; padding: 2.5rem 1.25rem; background: #fdf2f8; font-family: 'Helvetica Neue', Arial, sans-serif;">
          <div style="max-width: 720px; margin: 0 auto; background: #ffffff; border-radius: 20px; padding: 2.25rem; box-shadow: 0 25px 70px rgba(99, 102, 241, 0.25);">
            <div style="font-size: 11px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: #7c3aed;">Ruby Browser Signal R1</div>
            <h1 style="margin: 0.75rem 0 0.25rem; font-size: 2.25rem; color: #4c1d95;">Dashboard</h1>
            <p id="session-user" style="margin: 0 0 1rem; font-size: 1rem; font-weight: 600; color: #312e81;">Signed in as #{escaped_user}</p>
            <p style="margin: 0 0 1rem; font-size: 1.05rem; color: #1f2937;">Seeded alerts are ready.</p>
            <p style="margin: 0 0 0.75rem; font-size: 0.95rem; line-height: 1.6; color: #374151;">
              Autonomous code agents read the issue instructions, make the smallest safe edit, and run the requested validation command before reporting the outcome. The dashboard surface documents that workflow so the next reviewer easily understands what changed and why.
            </p>
            <p style="margin: 0; font-size: 0.95rem; line-height: 1.6; color: #4b5563;">
              A healthy run keeps the edit scope tight, executes the requested checks, and publishes artifacts so the repair remains auditable and reproducible.
            </p>
          </div>
        </section>
      HTML
    }
  end
end
