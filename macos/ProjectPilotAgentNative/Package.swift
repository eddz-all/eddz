// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "ProjectPilotAgentNative",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(
            name: "ProjectPilotAgentNative",
            targets: ["ProjectPilotAgentNative"]
        )
    ],
    targets: [
        .executableTarget(
            name: "ProjectPilotAgentNative",
            path: "Sources"
        )
    ]
)
