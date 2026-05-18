import SwiftUI

struct ConnectionFormView: View {
    @ObservedObject var store: AgentStore

    var body: some View {
        GroupBox("Connection") {
            Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 12) {
                GridRow {
                    Text("Backend URL")
                        .foregroundStyle(.secondary)
                    TextField("http://127.0.0.1:8000", text: $store.configuration.serverURL)
                        .textFieldStyle(.roundedBorder)
                }

                GridRow {
                    Text("Agent Token")
                        .foregroundStyle(.secondary)
                    SecureField(store.configuration.maskedToken.isEmpty ? "Required" : "Leave blank to keep saved token", text: $store.tokenInput)
                        .textFieldStyle(.roundedBorder)
                }

                GridRow {
                    Text("Machine ID")
                        .foregroundStyle(.secondary)
                    TextField("eddz-mac", text: $store.configuration.machineID)
                        .textFieldStyle(.roundedBorder)
                }

                GridRow {
                    Text("Allowed Root")
                        .foregroundStyle(.secondary)
                    HStack(spacing: 8) {
                        TextField("/Users/eddz/work", text: $store.configuration.allowedRoot)
                            .textFieldStyle(.roundedBorder)
                        Button {
                            store.chooseAllowedRoot()
                        } label: {
                            Label("Choose", systemImage: "folder")
                        }
                    }
                }

                GridRow {
                    Text("Interval")
                        .foregroundStyle(.secondary)
                    Stepper(value: $store.configuration.interval, in: 1...60, step: 1) {
                        Text("\(Int(store.configuration.interval)) seconds")
                            .monospacedDigit()
                    }
                }
            }

            HStack(spacing: 10) {
                Button {
                    store.saveConfiguration()
                } label: {
                    Label("Save", systemImage: "square.and.arrow.down")
                }

                Button {
                    store.pollOnce()
                } label: {
                    Label("Poll Once", systemImage: "arrow.clockwise")
                }
                .disabled(store.isRunning)

                Button {
                    store.isRunning ? store.stopAgent() : store.startAgent()
                } label: {
                    Label(store.isRunning ? "Stop" : "Start", systemImage: store.isRunning ? "stop.fill" : "play.fill")
                }
                .buttonStyle(.borderedProminent)

                Spacer()
            }
            .padding(.top, 10)

            if !store.message.isEmpty {
                Text(store.message)
                    .font(.callout)
                    .foregroundStyle(store.message == "Saved." ? Color.secondary : Color.red)
                    .padding(.top, 4)
            }
        }
    }
}
