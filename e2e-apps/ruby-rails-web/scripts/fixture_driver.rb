#!/usr/bin/env ruby
# frozen_string_literal: true

require "json"
require "fileutils"
require "uri"

action = ARGV[0].to_s
fixture = ARGV[1].to_s

if action.empty? || fixture.empty?
  warn "usage: fixture_driver.rb <prepare|auth-state> <fixture> [output_path] [entry_url]"
  exit 1
end

case action
when "prepare"
  puts "prepared fixture #{fixture}"
when "auth-state"
  output_path = ARGV[2].to_s
  entry_url = ARGV[3].to_s
  if output_path.empty?
    warn "auth-state requires an output path"
    exit 1
  end

  FileUtils.mkdir_p(File.dirname(output_path))
  origin =
    begin
      uri = URI.parse(entry_url.empty? ? "http://127.0.0.1:3101" : entry_url)
      "#{uri.scheme}://#{uri.host}:#{uri.port}"
    rescue URI::InvalidURIError
      "http://127.0.0.1:3101"
    end
  state = {
    cookies: [
      {
        name: "healer_session",
        value: fixture,
        domain: "127.0.0.1",
        path: "/",
        httpOnly: false,
        secure: false,
        sameSite: "Lax"
      }
    ],
    origins: [
      {
        origin: origin,
        localStorage: [
          { name: "fixture_profile", value: fixture }
        ]
      }
    ]
  }
  File.write(output_path, JSON.pretty_generate(state))
  puts "wrote auth state for #{fixture}"
else
  warn "unsupported action: #{action}"
  exit 1
end
