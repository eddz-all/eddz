import Foundation

enum ConfigFileStore {
    static func load() -> ExecutorConfiguration? {
        let url = AppPaths.configURL
        guard FileManager.default.fileExists(atPath: url.path) else {
            return nil
        }

        do {
            let data = try Data(contentsOf: url)
            return try JSONDecoder().decode(ExecutorConfiguration.self, from: data)
        } catch {
            return nil
        }
    }

    static func save(_ configuration: ExecutorConfiguration) throws {
        let url = AppPaths.configURL
        let directory = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(configuration)
        try data.write(to: url, options: [.atomic])
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
}
