import AppKit
import SwiftUI

@main
struct ProjectPilotAgentNativeApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var store = AgentStore()

    var body: some Scene {
        WindowGroup("ProjectPilot Agent") {
            ContentView(store: store)
                .frame(minWidth: 820, minHeight: 540)
        }
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandMenu("Agent") {
                Button("Start") {
                    store.startAgent()
                }
                .keyboardShortcut("r", modifiers: [.command])
                .disabled(store.isRunning)

                Button("Stop") {
                    store.stopAgent()
                }
                .keyboardShortcut(".", modifiers: [.command])
                .disabled(!store.isRunning)

                Divider()

                Button("Poll Once") {
                    store.pollOnce()
                }
                .keyboardShortcut("p", modifiers: [.command])
            }
        }

        Settings {
            SettingsView(store: store)
                .frame(width: 520)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }
}
