import Foundation

@MainActor
final class ExecutorProcessController: ObservableObject {
    @Published private(set) var isRunning = false
    @Published private(set) var output = ""
    @Published private(set) var lastError: String?

    private var process: Process?

    func start() {
        guard !isRunning else { return }

        do {
            let process = try makeProcess(arguments: ["-m", "projectpilot", "executor", "connect"])
            attachOutput(to: process)
            try process.run()
            self.process = process
            isRunning = true
            lastError = nil

            process.terminationHandler = { [weak self] process in
                Task { @MainActor in
                    self?.isRunning = false
                    self?.appendLine("Executor stopped with status \(process.terminationStatus).")
                }
            }
        } catch {
            lastError = error.localizedDescription
            appendLine("Start failed: \(error.localizedDescription)")
        }
    }

    func stop() {
        process?.terminate()
        process = nil
        isRunning = false
        appendLine("Stop requested.")
    }

    func pollOnce(completion: @escaping @MainActor @Sendable (String) -> Void) {
        do {
            let process = try makeProcess(arguments: ["-m", "projectpilot", "executor", "connect", "--once", "--json"])
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe

            process.terminationHandler = { [weak self] _ in
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let text = String(data: data, encoding: .utf8) ?? ""
                Task { @MainActor in
                    self?.appendLine(text.trimmingCharacters(in: .whitespacesAndNewlines))
                    completion(text)
                }
            }

            try process.run()
        } catch {
            lastError = error.localizedDescription
            appendLine("Poll failed: \(error.localizedDescription)")
            completion("")
        }
    }

    private func makeProcess(arguments: [String]) throws -> Process {
        let root = AppPaths.repositoryRoot()
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = arguments
        process.currentDirectoryURL = root

        var environment = ProcessInfo.processInfo.environment
        let existingPath = environment["PYTHONPATH"]
        environment["PYTHONPATH"] = [root.path, existingPath].compactMap { $0 }.joined(separator: ":")
        environment["PROJECTPILOT_REPO_ROOT"] = root.path
        process.environment = environment
        return process
    }

    private func attachOutput(to process: Process) {
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else {
                return
            }
            Task { @MainActor in
                self?.appendLine(text.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }
    }

    private func appendLine(_ line: String) {
        guard !line.isEmpty else { return }
        if output.isEmpty {
            output = line
        } else {
            output += "\n\(line)"
        }
    }
}
