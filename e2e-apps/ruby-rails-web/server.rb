require "cgi"
require "json"
require "webrick"
require_relative "config/routes"
require_relative "app/controllers/health_controller"
require_relative "app/controllers/sessions_controller"
require_relative "app/controllers/dashboard_controller"

HOST = ENV.fetch("HOST", "127.0.0.1")
PORT = Integer(ENV.fetch("PORT", "3101"))
SESSION_COOKIE = "healer_session"

server = WEBrick::HTTPServer.new(
  Port: PORT,
  BindAddress: HOST,
  AccessLog: [],
  Logger: WEBrick::Log.new($stderr, WEBrick::Log::WARN)
)

server.mount_proc "/" do |request, response|
  route = ROUTES[[request.request_method, request.path]]
  unless route
    response.status = 404
    response["Content-Type"] = "application/json"
    response.body = JSON.generate(error: "not_found")
    next
  end

  controller_name, action = route
  controller = Object.const_get(controller_name).new
  session_user = CGI.unescape(
    request.cookies.find { |cookie| cookie.name == SESSION_COOKIE }&.value.to_s
  )
  result = controller.public_send(action, request: request, session_user: session_user)

  response.status = Integer(result.fetch(:status, 200))
  response["Content-Type"] = result.fetch(:content_type, "text/plain")
  response["Location"] = result[:location] if result[:location]

  if result[:clear_cookie]
    response["Set-Cookie"] = "#{SESSION_COOKIE}=; Path=/; Max-Age=0"
  elsif result[:cookie_value]
    response["Set-Cookie"] = "#{SESSION_COOKIE}=#{CGI.escape(result[:cookie_value])}; Path=/"
  end

  response.body = String(result.fetch(:body, ""))
end

trap("INT") { server.shutdown }
trap("TERM") { server.shutdown }
server.start
