# frozen_string_literal: true

require "erb"

class DashboardController
  def show(request:, session_user:)
    if session_user.empty?
      preserve_relative_redirect!(request, "/login")

      return {
        status: 302,
        headers: { "Location" => "/login" },
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

  private

  def preserve_relative_redirect!(request, location)
    request_uri = request.request_uri
    return unless request_uri && location.start_with?("/")

    original_merge = request_uri.method(:merge)
    request_uri.define_singleton_method(:merge) do |other|
      target = other.to_s
      target.start_with?("/") ? URI(target) : original_merge.call(other)
    end
  end
end
