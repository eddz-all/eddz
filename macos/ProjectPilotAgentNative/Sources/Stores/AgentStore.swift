import Combine
import Foundation

@MainActor
final class AgentStore: ObservableObject {
    @Published var configuration: AgentConfiguration
    @Published var tokenInput = ""
    @Published var message = ""
    @Published var pollResult = "{}"
    @Published var hasSavedConfiguration = false

    private let processController = AgentProcessController()
    private var cancellables: Set<AnyCancellable> = []

    var isRunning: Bool {
        processController.isRunning
    }

    var output: String {
        processController.output
    }

    var lastError: String? {
        processController.lastError
    }

    init() {
        if let saved = ConfigFileStore.load() {
            configuration = saved
            hasSavedConfiguration = true
        } else {
            configuration = .empty
            hasSavedConfiguration = false
        }

        processController.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)
    }

    @discardableResult
    func saveConfiguration() -> Bool {
        do {
            var next = configuration
            if !tokenInput.isEmpty {
                next.token = tokenInput
            }
            try validate(next)
            try ConfigFileStore.save(next)
            configuration = next
            tokenInput = ""
            hasSavedConfiguration = true
            message = "Saved."
            return true
        } catch {
            message = error.localizedDescription
            return false
        }
    }

    func chooseAllowedRoot() {
        if let selected = FolderPicker.chooseFolder(startingAt: configuration.allowedRoot) {
            configuration.allowedRoot = selected
        }
    }

    func startAgent() {
        guard saveConfiguration() else { return }
        processController.start()
    }

    func stopAgent() {
        processController.stop()
    }

    func pollOnce() {
        guard saveConfiguration() else { return }
        processController.pollOnce { [weak self] output in
            self?.pollResult = output.isEmpty ? "{}" : output
        }
    }

    private func validate(_ configuration: AgentConfiguration) throws {
        if configuration.serverURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            throw ValidationError("Backend URL is required.")
        }
        if configuration.token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            throw ValidationError("Agent token is required.")
        }
        if configuration.allowedRoot.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            throw ValidationError("Allowed root is required.")
        }
        if !FileManager.default.fileExists(atPath: configuration.allowedRoot) {
            throw ValidationError("Allowed root does not exist.")
        }
        if configuration.interval <= 0 {
            throw ValidationError("Interval must be greater than 0.")
        }
    }
}

struct ValidationError: LocalizedError {
    let message: String

    init(_ message: String) {
        self.message = message
    }

    var errorDescription: String? {
        message
    }
}
