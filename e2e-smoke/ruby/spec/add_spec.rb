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

  it "returns zero when no operands are provided" do
    expect(add_many).to eq(0)
  end

  it "returns the single operand when only one number is provided" do
    expect(add_many(7)).to eq(7)
  end

  it "adds a longer list of integers" do
    expect(add_many(1, 2, 3, 4, 5)).to eq(15)
  end
end
