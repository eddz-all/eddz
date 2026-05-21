// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "ProjectPilotExecutorNative",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(
            name: "ProjectPilotExecutorNative",
            targets: ["ProjectPilotExecutorNative"]
        )
    ],
    targets: [
        .executableTarget(
            name: "ProjectPilotExecutorNative",
            path: "Sources"
        )
    ]
)
