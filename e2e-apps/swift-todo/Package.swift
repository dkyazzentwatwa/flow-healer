// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "FlowHealerSwiftTodoSandbox",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .library(name: "TodoCore", targets: ["TodoCore"]),
        .executable(name: "todo-cli", targets: ["TodoCLI"]),
    ],
    targets: [
        .target(
            name: "TodoCore"
        ),
        .executableTarget(
            name: "TodoCLI",
            dependencies: ["TodoCore"]
        ),
        .testTarget(
            name: "TodoCoreTests",
            dependencies: ["TodoCore"]
        ),
        .testTarget(
            name: "TodoCLITests",
            dependencies: ["TodoCLI", "TodoCore"]
        ),
    ]
)
