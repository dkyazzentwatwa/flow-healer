// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "FlowHealerAdd",
    products: [
        .library(name: "FlowHealerAdd", targets: ["FlowHealerAdd"]),
    ],
    targets: [
        .target(name: "FlowHealerAdd"),
        .testTarget(name: "FlowHealerAddTests", dependencies: ["FlowHealerAdd"]),
    ]
)
