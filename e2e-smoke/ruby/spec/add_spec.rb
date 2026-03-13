require_relative "../lib/add"

RSpec.describe "#add" do
  it "adds two numbers" do
    expect(add(2, 3)).to eq(5)
  end
end

RSpec.describe "#add_many" do
  it "adds positive integers" do
    expect(add_many(2, 3, 4)).to eq(9)
  end

  it "adds mixed-sign integers" do
    expect(add_many(-2, 3, -4)).to eq(-3)
  end
end
