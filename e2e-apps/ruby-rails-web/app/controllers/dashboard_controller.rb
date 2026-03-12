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

    {
      status: 200,
      content_type: "text/html",
      body: <<~HTML
        <h1>Dashboard</h1>
        <p id="session-user">#{ERB::Util.html_escape(session_user)}</p>
        <p>Seeded alerts are ready.</p>
      HTML
    }
  end
end
