require_relative "../add"

RSpec.describe "add" do
  it "returns the sum" do
    expect(add(2, 3)).to eq(5)
  end
end
