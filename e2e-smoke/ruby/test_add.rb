require "minitest/autorun"
require_relative "add"

class TestAdd < Minitest::Test
  def test_add_returns_sum
    assert_equal 5, add(2, 3)
  end
end
