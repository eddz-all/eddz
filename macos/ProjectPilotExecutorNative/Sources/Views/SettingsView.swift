import SwiftUI

struct SettingsView: View {
    @ObservedObject var store: ExecutorStore

    var body: some View {
        Form {
            TextField("Backend URL", text: $store.configuration.serverURL)
            SecureField(store.configuration.maskedToken.isEmpty ? "Executor token" : "Leave blank to keep saved token", text: $store.tokenInput)
            TextField("Executor ID", text: $store.configuration.executorID)

            HStack {
                TextField("Allowed Root", text: $store.configuration.allowedRoot)
                Button("Choose") {
                    store.chooseAllowedRoot()
                }
            }

            Stepper(value: $store.configuration.interval, in: 1...60, step: 1) {
                Text("Poll every \(Int(store.configuration.interval)) seconds")
            }

            HStack {
                Spacer()
                Button("Save") {
                    store.saveConfiguration()
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding()
    }
}
