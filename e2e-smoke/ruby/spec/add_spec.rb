require_relative "../lib/add"

RSpec.describe "#add" do
  it "adds two numbers" do
    expect(add(2, 3)).to eq(5)
  end
end
