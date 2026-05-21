import Foundation

enum AppPaths {
    static var configURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".projectpilot", isDirectory: true)
            .appendingPathComponent("executor.json")
    }

    static func repositoryRoot() -> URL {
        if let override = ProcessInfo.processInfo.environment["PROJECTPILOT_REPO_ROOT"] {
            return URL(fileURLWithPath: override).standardizedFileURL
        }

        let bundleURL = Bundle.main.bundleURL.standardizedFileURL
        let candidates = [
            bundleURL.deletingLastPathComponent().deletingLastPathComponent(),
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
            bundleURL
        ]

        for candidate in candidates {
            if let root = findRepositoryRoot(startingAt: candidate) {
                return root
            }
        }

        return URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    }

    private static func findRepositoryRoot(startingAt url: URL) -> URL? {
        var candidate = url.standardizedFileURL
        let fileManager = FileManager.default

        while true {
            let pyproject = candidate.appendingPathComponent("pyproject.toml").path
            let package = candidate.appendingPathComponent("projectpilot", isDirectory: true).path
            if fileManager.fileExists(atPath: pyproject), fileManager.fileExists(atPath: package) {
                return candidate
            }

            let parent = candidate.deletingLastPathComponent()
            if parent.path == candidate.path {
                return nil
            }
            candidate = parent
        }
    }
}
