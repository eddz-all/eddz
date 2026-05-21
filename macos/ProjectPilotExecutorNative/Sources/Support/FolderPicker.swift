import AppKit
import Foundation

enum FolderPicker {
    @MainActor
    static func chooseFolder(startingAt path: String) -> String? {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = true
        panel.directoryURL = URL(fileURLWithPath: path, isDirectory: true)

        guard panel.runModal() == .OK else {
            return nil
        }
        return panel.url?.path
    }
}
