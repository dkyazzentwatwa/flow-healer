require "net/http"
require "timeout"
require "uri"

APP_ROOT = File.expand_path("../..", __dir__)
TEST_PORT = 3111

def http_get(path, cookie: nil)
  uri = URI("http://127.0.0.1:#{TEST_PORT}#{path}")
  request = Net::HTTP::Get.new(uri)
  request["Cookie"] = cookie if cookie
  Net::HTTP.start(uri.host, uri.port) { |http| http.request(request) }
end

def http_post(path, form:)
  uri = URI("http://127.0.0.1:#{TEST_PORT}#{path}")
  request = Net::HTTP::Post.new(uri)
  request.set_form_data(form)
  Net::HTTP.start(uri.host, uri.port) { |http| http.request(request) }
end

RSpec.describe "Ruby rails web reference app" do
  before(:all) do
    @server_pid = Process.spawn(
      { "PORT" => TEST_PORT.to_s },
      "ruby",
      "server.rb",
      chdir: APP_ROOT,
      out: File::NULL,
      err: File::NULL
    )

    Timeout.timeout(5) do
      loop do
        response = http_get("/healthz")
        break if response.code == "200"
      rescue Errno::ECONNREFUSED
        sleep 0.1
      end
    end
  end

  after(:all) do
    Process.kill("TERM", @server_pid)
    Process.wait(@server_pid)
  rescue Errno::ESRCH, Errno::ECHILD
    nil
  end

  it "returns ok from /healthz" do
    response = http_get("/healthz")

    expect(response.code).to eq("200")
    expect(response.body).to include('"status":"ok"')
  end

  it "issues a cookie-backed session that the dashboard renders" do
    anonymous = http_get("/dashboard")

    expect(anonymous.code).to eq("302")
    expect(anonymous["Location"]).to eq("/login")

    response = http_post("/login", form: { "email" => "seeded-admin@example.com" })
    cookie = response["Set-Cookie"]

    expect(response.code).to eq("302")
    expect(cookie).to include("healer_session=seeded-admin%40example.com")

    dashboard = http_get("/dashboard", cookie: cookie)
    expect(dashboard.code).to eq("200")
    expect(dashboard.body).to include("seeded-admin@example.com")
  end
end
