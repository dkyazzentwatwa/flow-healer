# frozen_string_literal: true

class SessionsController
  def new(request:, session_user:)
    {
      status: 200,
      content_type: "text/html",
      body: <<~HTML
        <h1>Ruby Rails Web</h1>
        <p class="fixture-profile">#{session_user.empty? ? "anonymous" : session_user}</p>
        <form action="/login" method="post">
          <label>Email <input name="email" type="email" /></label>
          <label>Password <input name="password" type="password" /></label>
          <button type="submit">Sign in</button>
        </form>
      HTML
    }
  end

  def create(request:, session_user:)
    email = request.query["email"].to_s.strip
    user = email.empty? ? "admin@example.com" : email
    {
      status: 302,
      location: "/dashboard",
      cookie_value: user,
      body: ""
    }
  end

  def destroy(request:, session_user:)
    {
      status: 302,
      location: "/login",
      clear_cookie: true,
      body: ""
    }
  end
end
