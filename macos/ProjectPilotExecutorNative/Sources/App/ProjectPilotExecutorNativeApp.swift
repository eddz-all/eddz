import AppKit
import SwiftUI

@main
struct ProjectPilotExecutorNativeApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var store = ExecutorStore()

    var body: some Scene {
        WindowGroup("ProjectPilot Executor") {
            ContentView(store: store)
                .frame(minWidth: 820, minHeight: 540)
        }
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandMenu("Executor") {
                Button("Start") {
                    store.startExecutor()
                }
                .keyboardShortcut("r", modifiers: [.command])
                .disabled(store.isRunning)

                Button("Stop") {
                    store.stopExecutor()
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
