import Foundation

struct AgentConfiguration: Codable, Equatable {
    var serverURL: String
    var token: String
    var machineID: String
    var allowedRoot: String
    var interval: Double

    enum CodingKeys: String, CodingKey {
        case serverURL = "server_url"
        case token
        case machineID = "machine_id"
        case allowedRoot = "allowed_root"
        case interval
    }

    static var empty: AgentConfiguration {
        AgentConfiguration(
            serverURL: "",
            token: "",
            machineID: Host.current().localizedName ?? "local-machine",
            allowedRoot: FileManager.default.homeDirectoryForCurrentUser.path,
            interval: 5
        )
    }

    var maskedToken: String {
        guard !token.isEmpty else { return "" }
        if token.count <= 8 {
            return String(repeating: "*", count: token.count)
        }
        return "\(token.prefix(4))...\(token.suffix(4))"
    }
}
